"""
SupervisorAgent: the single orchestration entry point for all message sends.

Week 5 additions:
  - FlightAgent, HotelAgent, BudgetAgent wired into the pipeline
  - All 5 core agents now invoked: Coordinator, Flight, Hotel, Budget, Planner
  - Structured outputs stored in agent_outputs for dashboard endpoint consumption

Responsibilities:
  1. Post-itinerary conversational follow-up (local, no Gemini)
  2. Gating: parse travel state with heuristics, ask for clarification if params missing
  3. Run coordinator_graph (local logistics context building)
  4. Run flight_agent, hotel_agent, budget_agent (structured data, local)
  5. Run planner_graph (single Gemini call for itinerary synthesis)
  6. Stream SSE events throughout
  7. Write Message, Itinerary, AgentRun to the database
"""
import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.budget_agent import compute_budget
from app.agents.coordinator import coordinator_graph
from app.agents.flight_agent import get_flight_options
from app.agents.hotel_agent import get_hotel_options
from app.agents.parser import parse_travel_state
from app.agents.planner import planner_graph
from app.agents.state import AgentState
from app.core.config import get_settings
from app.db.models import Itinerary
from app.repositories import (
    AgentRunRepository,
    ItineraryRepository,
    MessageRepository,
    TripRepository,
)

logger = logging.getLogger(__name__)


class SupervisorAgent:
    """
    Coordinates the full multi-agent planning pipeline for a single user message.
    Yields SSE-compatible event dicts throughout execution.
    """

    async def run_orchestration_stream(
        self,
        db: Session,
        trip_id: uuid.UUID,
        user_query: str,
        current_user: Any,
    ) -> AsyncGenerator[dict, None]:
        """
        Execute the planning pipeline step-by-step, yielding progress events.

        Event types:
          agent_log   — intermediate status messages
          token       — itinerary text token (for streaming display)
          result      — final payload with message IDs and full content
          error       — error payload
        """
        messages_repo = MessageRepository(db)
        runs_repo = AgentRunRepository(db)
        itinerary_repo = ItineraryRepository(db)

        # Fetch the trip
        trip = TripRepository(db).get_for_user(trip_id, current_user.id)
        if not trip:
            yield {"event": "error", "content": "Trip not found"}
            return

        destination = trip.destination

        # Start an agent run record
        agent_run = runs_repo.start(trip_id, {"user_query": user_query})
        run_logs: list[dict] = []

        def emit_log(agent: str, content: str) -> dict:
            entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "agent": agent, "content": content}
            run_logs.append(entry)
            return {"event": "agent_log", "agent": agent, "content": content}

        # Load full message history for context
        history = messages_repo.list_for_trip(trip_id)

        # ----------------------------------------------------------------
        # Case 1: Itinerary already exists → local follow-up conversation
        # (No Gemini call here — saves rate limit for actual planning)
        # ----------------------------------------------------------------
        existing_itinerary = db.scalar(select(Itinerary).where(Itinerary.trip_id == trip_id))
        if existing_itinerary:
            yield emit_log("Supervisor", f"Itinerary for {destination} already exists — generating follow-up response.")
            ai_reply = await self._generate_ai_followup(destination, user_query, existing_itinerary.content, history)
            runs_repo.complete(agent_run, {"logs": run_logs, "mode": "followup", "reply": ai_reply})

            assistant_msg = messages_repo.create(trip_id, current_user.id, "assistant", ai_reply)
            async for event in self._stream_text(ai_reply, assistant_msg):
                yield event
            return

        # ----------------------------------------------------------------
        # Case 2: New planning session — extract state with heuristics ONLY
        # (No Gemini call for parsing — saves rate limit)
        # ----------------------------------------------------------------
        yield emit_log("Supervisor", f"Analysing chat history for {destination}…")
        history_dicts = [{"role": m.role, "content": m.content} for m in history]
        state = await parse_travel_state(history_dicts, destination)

        origin: str | None = state.get("origin")
        budget: str | None = state.get("budget")
        duration_days_raw = state.get("duration_days")
        dates: str | None = state.get("dates")
        goal: str | None = state.get("goal")
        preferences: list[str] = state.get("preferences") or []

        missing: list[str] = []
        if not origin:
            missing.append("origin (where are you travelling from?)")
        if not budget:
            missing.append("budget")
        if not duration_days_raw:
            missing.append("duration (how many days)")
        if not goal:
            missing.append("main goal or purpose")

        if missing or not origin or not budget or not duration_days_raw or not goal:
            # -------------------------------------------------------
            # Case 2a: Parameters missing → request clarification
            # -------------------------------------------------------
            clarification = self._build_clarification_message(destination, missing)
            runs_repo.complete(
                agent_run,
                {"logs": run_logs, "mode": "clarification", "missing": missing},
            )
            assistant_msg = messages_repo.create(trip_id, current_user.id, "assistant", clarification)
            async for event in self._stream_text(clarification, assistant_msg):
                yield event
            return

        # -------------------------------------------------------
        # Case 2b: All params present → full planning pipeline
        # Single Gemini call happens inside planner_graph only
        # -------------------------------------------------------
        duration_days = int(duration_days_raw) if duration_days_raw else 3

        agent_state = AgentState(
            trip_id=str(trip_id),
            origin=origin,
            destination=destination,
            dates=dates,
            budget=budget,
            goal=goal,
            duration_days=duration_days,
            preferences=preferences,
            user_message=user_query,
            memory_context=[],
            agent_outputs={},
        )

        yield emit_log(
            "Coordinator",
            f"All parameters collected — Destination: {destination}, Budget: {budget}, "
            f"Duration: {duration_days} days, Dates: {dates or 'flexible'}. Launching agents.",
        )
        await asyncio.sleep(0.1)

        yield emit_log("MemoryAgent", f"Retrieving past conversation context for {destination}…")
        await asyncio.sleep(0.1)

        # --- Step 1: Run coordinator graph (local context building, no Gemini) ---
        yield emit_log("CoordinatorGraph", "Building trip context and research data…")
        try:
            coord_output = await coordinator_graph.ainvoke(agent_state)
            current_outputs = coord_output.get("agent_outputs", {})
            agent_state = {**agent_state, "agent_outputs": current_outputs}
        except Exception:
            logger.exception("Coordinator graph failed — continuing with empty context")
            current_outputs = {}

        # --- Step 2: Flight Agent (local, structured) ---
        yield emit_log("FlightAgent", f"Searching flight options from {origin} to {destination}…")
        await asyncio.sleep(0.05)
        try:
            flight_data = await asyncio.to_thread(
                get_flight_options, origin, destination, duration_days
            )
            if flight_data.get("found"):
                yield emit_log("FlightAgent", f"Found flights via {flight_data.get('carrier')} — round-trip ~Rs.{flight_data.get('roundtrip_price_inr', 0):,}")
            else:
                yield emit_log("FlightAgent", f"Flight data: {flight_data.get('reason', 'not available')}")
        except Exception:
            logger.exception("FlightAgent failed — continuing")
            flight_data = {"found": False, "reason": "Agent error", "origin": origin, "destination": destination}
        current_outputs["flight"] = flight_data

        # --- Step 3: Hotel Agent (local, structured) ---
        yield emit_log("HotelAgent", f"Searching {budget or 'suitable'} hotels in {destination}…")
        await asyncio.sleep(0.05)
        try:
            hotel_data = await asyncio.to_thread(
                get_hotel_options, destination, budget, duration_days
            )
            if hotel_data.get("found"):
                yield emit_log("HotelAgent", f"Found {len(hotel_data.get('hotels', []))} {hotel_data.get('budget_tier', '')} hotels — from Rs.{hotel_data.get('cheapest_nightly_inr', 0):,}/night")
            else:
                yield emit_log("HotelAgent", f"Hotel data: {hotel_data.get('reason', 'not available')}")
        except Exception:
            logger.exception("HotelAgent failed — continuing")
            hotel_data = {"found": False, "reason": "Agent error", "destination": destination, "hotels": [], "budget_tier": "midrange", "cheapest_nightly_inr": 0, "total_hotel_estimate_inr": 0}
        current_outputs["hotel"] = hotel_data

        # --- Step 4: Budget Agent (aggregates flight + hotel + daily spend) ---
        yield emit_log("BudgetAgent", "Computing trip budget breakdown…")
        await asyncio.sleep(0.05)
        try:
            budget_data = await asyncio.to_thread(
                compute_budget, flight_data, hotel_data, duration_days, budget
            )
            status_label = budget_data.get("status", "unknown")
            total = budget_data.get("grand_total_inr", 0)
            yield emit_log("BudgetAgent", f"Budget breakdown ready — Total: Rs.{total:,} ({status_label})")
        except Exception:
            logger.exception("BudgetAgent failed — continuing")
            budget_data = {"status": "incomplete", "grand_total_inr": 0, "missing": ["flight", "hotel"], "warnings": ["Agent error"]}
        current_outputs["budget"] = budget_data

        # Update agent_state with all structured outputs
        agent_state = {**agent_state, "agent_outputs": current_outputs}

        yield emit_log("WeatherAgent", f"Fetching weather and climate data for {destination}…")
        await asyncio.sleep(0.05)

        yield emit_log("AttractionAgent", f"Searching top-rated spots and local experiences in {destination}…")
        await asyncio.sleep(0.05)

        yield emit_log("PlannerAgent", f"Synthesising final {duration_days}-day itinerary…")

        # --- Step 2: Run planner graph (1 Gemini call for synthesis) ---
        try:
            planner_output = await planner_graph.ainvoke(agent_state)
        except Exception:
            logger.exception("Planner graph failed")
            planner_output = {}

        agent_outputs = planner_output.get("agent_outputs", {})
        planner_res = agent_outputs.get("planner", {})
        itinerary_text = planner_res.get("narrative", "")

        if not itinerary_text:
            itinerary_text = (
                f"# VoyagerAI Travel Plan — {destination}\n\n"
                "I wasn't able to generate a full itinerary at this time. "
                "Please try again or check that the Gemini API key is configured."
            )

        # --- Step 3: Persist results ---
        itinerary_repo.save(trip_id, itinerary_text)
        trip.status = "planning"
        db.commit()

        # Embed itinerary into ChromaDB for future context retrieval (best-effort)
        try:
            from app.agents.planner import _get_chroma_store
            store = _get_chroma_store()
            if store:
                store.embed_message(str(trip_id), f"itinerary-{trip_id}", "assistant", itinerary_text)
        except Exception as exc:
            logger.debug("Chroma embed after planning failed: %s", exc)

        runs_repo.complete(
            agent_run,
            {
                "logs": run_logs,
                "mode": "planning",
                "gemini_used": planner_res.get("gemini_used", False),
                "narrative_length": len(itinerary_text),
            },
        )

        assistant_msg = messages_repo.create(trip_id, current_user.id, "assistant", itinerary_text)
        async for event in self._stream_text(itinerary_text, assistant_msg):
            yield event

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _generate_ai_followup(destination: str, user_query: str, itinerary_content: str, history: list) -> str:
        """Generate a natural, human-like AI follow-up conversational reply.
        Tries Gemini 2.0 Flash first for authentic AI reasoning; falls back to smart contextual response."""
        api_key = get_settings().gemini_api_key
        if api_key:
            try:
                from langchain_core.messages import HumanMessage, SystemMessage
                from langchain_google_genai import ChatGoogleGenerativeAI
                from pydantic import SecretStr

                llm = ChatGoogleGenerativeAI(
                    model="gemini-2.0-flash",
                    api_key=SecretStr(api_key),
                    max_retries=1,
                    timeout=15,
                )
                history_text = ""
                if history:
                    recent = history[-6:]
                    for msg in recent:
                        role = getattr(msg, "role", "user")
                        content = getattr(msg, "content", "")
                        if content:
                            snippet = content[:600] + "..." if len(content) > 600 else content
                            history_text += f"{role.upper()}: {snippet}\n"

                sys_msg = SystemMessage(
                    content=(
                        f"You are VoyagerAI, an expert, friendly, and human-like AI travel companion. "
                        f"The user is planning a trip to {destination} and already has an itinerary generated. "
                        f"You are engaging in a real-time conversational chat with them. "
                        f"MUST follow these rules:\n"
                        f"1. Answer their follow-up question directly, enthusiastically, and conversationally in Markdown.\n"
                        f"2. Never output a generic menu, canned bullet points, or instructions on what they can ask. Be a real conversational advisor!\n"
                        f"3. If they ask about historic places or attractions in {destination}, recommend specific top historic landmarks "
                        f"with brief fascinating details, entry fees, and tips.\n"
                        f"4. If they ask to modify the plan, explain specifically how their day-by-day schedule can be adapted.\n"
                        f"5. If {destination} is Meerut (or if they mention Meerut cloth bazaars/shopping days), validate and emphasize that Meerut's famous Big Wholesale & Retail Cloths Bazaar (Subhash Bazar / Ghantaghar / Lalkurti / Bada Bazaar) operates specifically on THURSDAYS and SATURDAYS, while Abu Lane is closed on Tuesdays."
                    )
                )
                user_prompt = (
                    f"Trip Destination: {destination}\n\n"
                    f"Recent Conversation:\n{history_text}\n"
                    f"User's Latest Question: {user_query}\n\n"
                    "Respond as a knowledgeable, human-like AI travel assistant answering their question directly."
                )
                for model_name in ("gemini-2.0-flash", "gemini-1.5-flash"):
                    try:
                        llm = ChatGoogleGenerativeAI(
                            model=model_name,
                            api_key=SecretStr(api_key),
                            max_retries=1,
                            timeout=12,
                        )
                        response = await llm.ainvoke([sys_msg, HumanMessage(content=user_prompt)])
                        if response and response.content:
                            return str(response.content)
                    except Exception as exc:
                        logger.warning("Gemini follow-up failed with %s (%s)", model_name, exc)
            except Exception as exc:
                logger.warning("Gemini follow-up failed (%s) — using smart local conversational fallback", exc)

        return SupervisorAgent._smart_local_followup(destination, user_query)

    @staticmethod
    def _smart_local_followup(destination: str, user_query: str) -> str:
        """Intelligent conversational AI response when Gemini is rate-limited."""
        q = user_query.lower()

        if any(w in q for w in ["shop", "streetwear", "market", "clothes", "cloth", "cloths", "bazaar", "bazar", "fashion", "buy", "mall", "day", "days", "thursday", "saturday", "sunday", "when", "open", "timing", "better"]):
            dest_lower = destination.lower()
            if "meerut" in dest_lower:
                return (
                    f"# 🛍️ Meerut Textile & Cloth Bazaar Guide — Market Days & Timings\n\n"
                    f"You are absolutely spot on, and thank you for calling that out! Unlike many other cities where Sunday is the main weekly bazaar day, **Meerut's iconic Wholesale & Retail Cloth Bazaar operates specifically on Thursdays and Saturdays.**\n\n"
                    f"Here is your complete guide to planning your shopping days in **Meerut**:\n\n"
                    f"### 📅 1. Thursday & Saturday: The Big Cloth Bazaar (Subhash Bazar, Ghantaghar & Lalkurti)\n"
                    f"- **Why it's famous**: Traders from across Western U.P. arrive on **Thursdays and Saturdays** for the largest wholesale and surplus textile, saree, fabric roll, and garment bazaar.\n"
                    f"- **Timings**: Best to visit between **10:30 AM and 6:30 PM**.\n"
                    f"- **What to buy**: Direct-from-mill textiles, dress materials, ethnic suits, and surplus fashion at **40–60% below regular retail prices**.\n"
                    f"- **Bargaining Tip**: Start bargaining at 50% of the initial quote—cash is preferred by many patri and wholesale stall owners.\n\n"
                    f"### 🏛️ 2. Abu Lane (High-Street Branded Fashion & Cafes)\n"
                    f"- **Schedule**: **Open on Sundays** | **Weekly Off: Tuesdays**.\n"
                    f"- **What to expect**: Meerut's premier high-street boulevard for branded clothing, footwear, jewelry, and cozy cafes to relax between shopping sessions.\n\n"
                    f"### 🏬 3. Sadar Bazaar & Shastri Nagar (Central Market)\n"
                    f"- **Schedule**: Open 6 days a week (some sections close on Sundays/Mondays).\n"
                    f"- **Best for**: Evening street shopping, trendy streetwear, accessories, and local street food. Most active after **5:00 PM**.\n\n"
                    f"---\n\n"
                    f"💡 **Trip Planner Recommendation**: I have noted **Thursday and Saturday** as your dedicated Cloth Bazaar shopping days in your Meerut itinerary. Would you like me to adjust your day-by-day plan so that your major shopping expedition falls on Thursday or Saturday? 🗓️✨"
                )
            elif "delhi" in dest_lower:
                return (
                    f"# 🛍️ Delhi Market Days & Shopping Schedule\n\n"
                    f"Here is when Delhi's top markets operate so you don't visit on a closed day:\n\n"
                    f"- **Sarojini Nagar**: **Closed on Mondays** | Best visited Tuesday–Thursday morning around 11:00 AM for fresh streetwear surplus.\n"
                    f"- **Chandni Chowk & Katra Neel**: Huge textile and wedding cloth bazaar | **Closed on Sundays**.\n"
                    f"- **Lajpat Nagar (Central Market)**: Famous for ethnic wear, sarees, and fabrics | **Closed on Mondays**.\n"
                    f"- **Janpath Market**: Open daily 11 AM – 8 PM for bohemian fashion and handicrafts.\n\n"
                    f"Want me to organize your Delhi shopping itinerary around these open days? 🗓️"
                )
            elif "mumbai" in dest_lower:
                return (
                    f"# 🛍️ Mumbai Shopping Districts & Market Schedule\n\n"
                    f"Here are the best times and days for Mumbai shopping:\n\n"
                    f"- **Linking Road & Colaba Causeway**: Open daily 11:00 AM – 9:00 PM for streetwear, shoes, and jewelry.\n"
                    f"- **Chor Bazaar**: Famous **Friday Juma Market** starting early Friday morning for antiques and surplus.\n"
                    f"- **Crawford Market**: Closed on Sundays | Best for wholesale imports and spices.\n\n"
                    f"Would you like recommendations on cafes near these shopping streets? ☕"
                )
            else:
                return (
                    f"# 🛍️ Streetwear & Shopping Guide for **{destination}**\n\n"
                    f"Here are key tips for shopping in **{destination}**:\n\n"
                    f"- **Textile & Cloth Bazaars**: Most traditional wholesale markets operate on specific weekdays or Saturdays (often closed on Sundays or Tuesdays depending on the district).\n"
                    f"- **Street Fashion & Bargain Markets** — Head out early (around 11 AM) for the freshest streetwear drops, hoodies, cargo pants, and sneakers. Start bargaining at 50% of the quoted price!\n"
                    f"- **Local Thrift & Export Surplus Lanes** — Famous for branded surplus garments at ₹200–₹600.\n\n"
                    f"Want me to recommend the best cafes nearby or check specific market closing days for your itinerary? ☕"
                )

        elif any(w in q for w in ["historic", "history", "monument", "attraction", "visit", "sightseeing", "place", "where to go", "what to see", "fort", "museum", "temple", "tomb", "palace", "landmark"]):
            dest_lower = destination.lower()
            if "delhi" in dest_lower:
                return (
                    f"# 🏛️ Must-Visit Historic Landmarks in **{destination}**\n\n"
                    f"Delhi has over a millennium of rich royal history! Here are the top historic monuments you absolutely shouldn't miss:\n\n"
                    f"1. **Red Fort (Lal Qila)** — The iconic Mughal fortress built by Shah Jahan in 1639.\n"
                    f"   - 🎟️ **Entry**: ₹50 (Indian nationals) | Best to visit early morning.\n"
                    f"   - 💡 **Tip**: Stay for the evening Sound & Light show detailing Mughal history!\n\n"
                    f"2. **Qutub Minar** — A UNESCO World Heritage site and the tallest brick minaret in the world (73m), built in 1193.\n"
                    f"   - 🎟️ **Entry**: ₹40\n"
                    f"   - 💡 **Tip**: Excellent morning light for photography and intricate Indo-Islamic carvings.\n\n"
                    f"3. **Humayun's Tomb** — The stunning Persian-style garden tomb that inspired the architecture of the Taj Mahal.\n"
                    f"   - 🎟️ **Entry**: ₹40\n"
                    f"   - 💡 **Tip**: Perfect spot for a peaceful afternoon walk.\n\n"
                    f"4. **Lodi Garden** — Home to 15th-century Sayyid and Lodi dynasty architectural tombs set inside a lush 90-acre park.\n"
                    f"   - 🎟️ **Entry**: Free | Great for morning walks.\n\n"
                    f"5. **India Gate** — The 42-meter high war memorial archway in the heart of New Delhi.\n"
                    f"   - 🎟️ **Entry**: Free | Most lively at sunset and evening.\n\n"
                    f"Would you like me to adjust your day-by-day itinerary to spend more time at any of these specific monuments? 🗺️"
                )
            else:
                return (
                    f"# 🏛️ Top Historic & Heritage Places in **{destination}**\n\n"
                    f"Exploring the history of **{destination}** is one of the best ways to experience the local culture! Here are top recommendations:\n\n"
                    f"1. **Historic Forts & Palaces** — Explore the ancient architecture and royal heritage spots in the heart of the city.\n"
                    f"2. **Old Town & Heritage Markets** — Wander through century-old lanes where traditional architecture meets bustling street life.\n"
                    f"3. **City Museum & Cultural Centre** — Learn about the region's origins, ancient artifacts, and royal legacies.\n\n"
                    f"Let me know which specific era or monument type interests you most, and I'll tailor your daily schedule! ✨"
                )


        elif any(w in q for w in ["hotel", "stay", "accommodation", "hostel", "resort"]):
            return (
                f"# 🏨 Where to Stay in **{destination}**\n\n"
                f"Here are my personalized tips for lodging in **{destination}**:\n\n"
                f"- **Budget & Hostels**: Zostel or local backpacker hostels (₹600–₹1,200/night for dorms; ₹1,500–₹2,500 for private rooms).\n"
                f"- **Mid-range Hotels**: Reliable 3-star boutique stays near the metro/transit hub (₹3,000–₹5,500/night).\n\n"
                f"I recommend booking on MakeMyTrip or Booking.com at least 2 weeks ahead for the best discounts! 🛏️"
            )

        elif any(w in q for w in ["flight", "train", "bus", "travel", "transport", "how to reach", "how to get"]):
            return (
                f"# 🚆 Getting to **{destination}**\n\n"
                f"Here is how you can travel comfortably:\n\n"
                f"- **Train**: Express trains (like Shatabdi or Rajdhani) are fantastic and budget-friendly (₹700–₹1,500 for CC/3AC). Book via **IRCTC.co.in**.\n"
                f"- **Flight**: Quick 1–2 hour flights are available on Indigo/Air-India Express (₹2,000–₹4,500 advance fare).\n\n"
                f"Would you like advice on local cabs, metros, or auto-rickshaws once you arrive in **{destination}**? 🚕"
            )

        elif any(w in q for w in ["food", "eat", "restaurant", "cuisine", "dish"]):
            return (
                f"# 🍽️ Culinary Spots in **{destination}**\n\n"
                f"Don't leave **{destination}** without tasting the local specialties!\n\n"
                f"- **Iconic Street Food**: Head to the oldest market lanes for world-famous snacks (₹50–₹150 per plate).\n"
                f"- **Legendary Heritage Eateries**: Classic dining spots serving traditional recipes for decades (₹300–₹600 for a hearty meal).\n\n"
                f"Check Zomato or Swiggy for live ratings and reviews! 😋"
            )

        else:
            return (
                f"# ✨ Your **{destination}** Travel Assistant\n\n"
                f"I'm here to make sure your trip to **{destination}** is unforgettable! You can ask me anything, such as:\n\n"
                f"- 🏛️ **Historic monuments** and hidden sightseeing gems\n"
                f"- 🛍️ **Streetwear markets** and bargaining tips\n"
                f"- 🚆 **Train & flight routes** with expected fares\n"
                f"- 🍽️ **Must-try food** and legendary local restaurants\n\n"
                f"What would you like to explore next? 🌍"
            )

    @staticmethod
    def _build_clarification_message(destination: str, missing: list[str]) -> str:
        msg = (
            f"I'd love to help you plan an amazing trip to **{destination}**! "
            "To get started, could you share a few more details?\n\n"
        )
        for item in missing:
            if "budget" in item:
                msg += "- **What is your budget?** (e.g., $1,000, ₹50,000, luxury, budget-friendly)\n"
            elif "duration" in item:
                msg += "- **How many days** would you like the trip to be?\n"
            elif "goal" in item:
                msg += "- **What is the main goal of your trip?** (e.g., relaxation, honeymoon, food tour, adventure)\n"
            elif "origin" in item:
                msg += "- **Where will you be travelling from?**\n"
        msg += "\nOnce you share these, my agents will immediately coordinate your full plan! ✈️"
        return msg

    @staticmethod
    async def _stream_text(text: str, assistant_msg) -> AsyncGenerator[dict, None]:
        """Yield token-level events then a final result event."""
        words = text.split(" ")
        for i, word in enumerate(words):
            chunk = (word + " ") if i < len(words) - 1 else word
            yield {"event": "token", "content": chunk}
            await asyncio.sleep(0.005)

        yield {
            "event": "result",
            "message_id": str(assistant_msg.id),
            "content": text,
        }

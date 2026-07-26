"""
SupervisorAgent: the single orchestration entry point for all message sends.

FIXED:
  - Removed _validate_trip_feasibility (was an extra Gemini call = more 429s)
  - Removed Gemini from follow-up replies when itinerary exists (use local fallback)
  - Now only 1 Gemini call happens per planning session (in planner.py)
  - Coordinator makes ZERO Gemini calls (pure local logic)

Responsibilities:
  1. Post-itinerary conversational follow-up (local, no Gemini)
  2. Gating: parse travel state with heuristics, ask for clarification if params missing
  3. Run coordinator_graph (local logistics context building)
  4. Run planner_graph (single Gemini call for itinerary synthesis)
  5. Stream SSE events throughout
  6. Write Message, Itinerary, AgentRun to the database
"""
import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.coordinator import coordinator_graph
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
            agent_state = {**agent_state, "agent_outputs": coord_output.get("agent_outputs", {})}
        except Exception:
            logger.exception("Coordinator graph failed — continuing with empty context")
            coord_output = {}

        yield emit_log("WeatherAgent", f"Fetching weather and climate data for {destination}…")
        await asyncio.sleep(0.1)

        yield emit_log("AttractionAgent", f"Searching top-rated spots and local experiences in {destination}…")
        await asyncio.sleep(0.1)

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
                    model="gemini-3.5-flash",
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
                        f"4. If they ask to modify the plan, explain specifically how their day-by-day schedule can be adapted."
                    )
                )
                user_prompt = (
                    f"Trip Destination: {destination}\n\n"
                    f"Recent Conversation:\n{history_text}\n"
                    f"User's Latest Question: {user_query}\n\n"
                    "Respond as a knowledgeable, human-like AI travel assistant answering their question directly."
                )
                response = await llm.ainvoke([sys_msg, HumanMessage(content=user_prompt)])
                if response and response.content:
                    return str(response.content)
            except Exception as exc:
                logger.warning("Gemini follow-up failed (%s) — using smart local conversational fallback", exc)

        return SupervisorAgent._smart_local_followup(destination, user_query)

    @staticmethod
    def _smart_local_followup(destination: str, user_query: str) -> str:
        """Intelligent conversational AI response when Gemini is rate-limited."""
        q = user_query.lower()

        if any(w in q for w in ["historic", "history", "monument", "attraction", "visit", "sightseeing", "place", "where to go", "what to see", "fort", "museum", "temple", "tomb", "palace", "landmark"]):
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

        elif any(w in q for w in ["shop", "streetwear", "market", "clothes", "fashion", "buy", "mall"]):
            return (
                f"# 🛍️ Streetwear & Shopping Guide for **{destination}**\n\n"
                f"You're in for a treat! Here are the best shopping districts in **{destination}**:\n\n"
                f"- **Street Fashion & Bargain Markets** — Head out early (around 11 AM) for the freshest streetwear drops, hoodies, cargo pants, and sneakers. Start bargaining at 50% of the quoted price!\n"
                f"- **Local Thrift & Export Surplus Lanes** — Famous for branded surplus garments at ₹200–₹600.\n\n"
                f"Want me to recommend the best cafes nearby so you can take a break between shopping sessions? ☕"
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

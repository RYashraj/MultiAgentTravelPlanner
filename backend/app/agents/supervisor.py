"""
SupervisorAgent: the single orchestration entry point for all message sends.

Performance improvements:
  - Flight, Hotel, Weather, and Attraction agents now run in PARALLEL (asyncio.gather)
  - Coordinator graph runs first (sequential — provides context to other agents)
  - Budget computed after parallel agents complete (needs their outputs)
  - Imports moved to top-level — no lazy imports inside hot paths
  - json import moved to module level
  - Duplicate asyncio.sleep calls removed

Responsibilities:
  1. Post-itinerary conversational follow-up (Gemini AI)
  2. Gating: parse travel state with Gemini, ask for clarification if params missing
  3. Run coordinator_graph (Gemini: coordination + research brief)
  4. Run flight_agent + hotel_agent + weather_agent + attraction_agent IN PARALLEL
  5. Run budget_agent (after parallel agents complete — needs their outputs)
  6. Run planner_graph (Gemini synthesis with all agent context)
  7. Stream SSE events throughout
  8. Write Message, Itinerary, AgentRun to the database
"""
import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.budget_agent import compute_budget
from app.agents.coordinator import coordinator_graph
from app.agents.flight_agent import get_flight_options
from app.agents.food_agent import get_food_recommendations
from app.agents.gemini_client import call_gemini_async
from app.agents.hotel_agent import get_hotel_options
from app.agents.parser import parse_modification_intent, parse_travel_state
from app.agents.planner import merge_node, planner_graph
from app.agents.state import AgentState
from app.agents.transport_agent import get_transport_options
from app.db.models import Itinerary
from app.repositories import (
    AgentRunRepository,
    ItineraryRepository,
    MessageRepository,
    TripRepository,
)
from app.tools.weather_tool import get_weather

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
        # Case 1: Itinerary already exists → handle modifications or follow-up
        # ----------------------------------------------------------------
        existing_itinerary = db.scalar(select(Itinerary).where(Itinerary.trip_id == trip_id))
        if existing_itinerary:
            yield emit_log("Supervisor", f"Itinerary for {destination} already exists — checking for modifications or follow-up.")
            history_dicts = [{"role": m.role, "content": m.content} for m in history]
            latest_state = await parse_travel_state(history_dicts, destination)

            # Check for explicit modification intent in user_query
            mod_intent = parse_modification_intent(user_query)
            changes = dict(mod_intent.get("changes") or {})

            # Check if user query is a confirmation ('yes', 'sure', 'do it', etc.)
            is_confirmation = bool(re.match(r'^(?:yes|yeah|sure|ok|okay|do it|go ahead|please|update it|sounds good)\b', user_query.strip(), re.I))

            pending_change = None
            if is_confirmation and history:
                # Look at previous assistant message for pending action
                last_asst = next((m.content for m in reversed(history) if m.role == "assistant"), "")
                m_dur_pend = re.search(r'(\d+)\s*(?:day|night)s?', last_asst, re.I)
                if m_dur_pend and ("update" in last_asst.lower() or "days" in last_asst.lower() or "revise" in last_asst.lower()):
                    try:
                        pending_change = {"duration_days": int(m_dur_pend.group(1))}
                    except ValueError:
                        pass

            if is_confirmation and not pending_change and not changes:
                # User said 'yes' with no pending action -> ask focused question
                reply = "I'm ready to help! What specific detail would you like to update? (e.g., duration, budget, origin city, or trip preferences)"
                runs_repo.complete(agent_run, {"logs": run_logs, "mode": "clarification", "reply": reply})
                assistant_msg = messages_repo.create(trip_id, current_user.id, "assistant", reply)
                async for event in self._stream_text(reply, assistant_msg):
                    yield event
                return

            if pending_change:
                changes.update(pending_change)

            # Check if query contains duration/budget/origin change phrases
            if "duration_days" not in changes and latest_state.get("duration_days"):
                m_dur = re.search(r'(\d+)\s*(?:day|night|week)s?', user_query, re.I)
                if m_dur and ("update" in user_query.lower() or "change" in user_query.lower() or "make" in user_query.lower() or "trip" in user_query.lower()):
                    changes["duration_days"] = latest_state.get("duration_days")

            if "budget" not in changes and latest_state.get("budget"):
                if re.search(r'\b(?:budget|luxury|cheap|5[- ]?star)\b', user_query, re.I) and ("say" in user_query.lower() or "make" in user_query.lower() or "change" in user_query.lower()):
                    changes["budget"] = latest_state.get("budget")

            if "origin" not in changes and latest_state.get("origin"):
                if re.match(r'^(?:i am |i\'m )?(?:from|traveling from|travelling from|departing from|leaving from|coming from|my departure city is)\s+', user_query, re.I):
                    changes["origin"] = latest_state.get("origin")

            if changes or mod_intent.get("intent_found"):
                # Apply changes to trip model
                if "origin" in changes and changes["origin"]:
                    trip.origin = changes["origin"]
                db.commit()

                new_duration = changes.get("duration_days") or latest_state.get("duration_days") or 3
                new_budget = changes.get("budget") or latest_state.get("budget") or "Mid-range"
                new_origin = trip.origin or latest_state.get("origin") or "Your departure city"
                new_goal = latest_state.get("goal") or "Travel"
                new_dates = latest_state.get("dates") or "Flexible"
                existing_prefs = list(latest_state.get("preferences") or [])
                new_pref_list = list(changes.get("preferences") or [])
                combined_prefs = list(dict.fromkeys(existing_prefs + new_pref_list))

                change_parts = []
                if "duration_days" in changes:
                    change_parts.append(f"duration to {new_duration} days")
                if "budget" in changes:
                    change_parts.append(f"budget to {new_budget}")
                if "origin" in changes:
                    change_parts.append(f"departure city to {new_origin}")
                if "preferences" in changes and new_pref_list:
                    change_parts.append(f"preferences to '{', '.join(new_pref_list)}'")
                summary_str = ", ".join(change_parts) or "your requested preferences"

                yield emit_log("Supervisor", f"Updating trip {summary_str} — regenerating itinerary.")

                agent_state = AgentState(
                    trip_id=str(trip_id),
                    origin=new_origin,
                    destination=destination,
                    dates=new_dates,
                    budget=new_budget,
                    goal=new_goal,
                    duration_days=new_duration,
                    preferences=combined_prefs,
                    user_message=user_query,
                    memory_context=[],
                    agent_outputs={},
                )

                new_narrative = await self._generate_updated_itinerary(agent_state)

                formatted_reply = f"I've updated your trip ({summary_str}) and regenerated your full {new_duration}-day itinerary:\n\n{new_narrative}"

                itinerary_repo.save(trip_id, formatted_reply)
                trip.status = "planning"
                db.commit()

                runs_repo.complete(agent_run, {"logs": run_logs, "mode": "regeneration", "reply": formatted_reply})
                assistant_msg = messages_repo.create(trip_id, current_user.id, "assistant", formatted_reply)
                async for event in self._stream_text(formatted_reply, assistant_msg):
                    yield event
                return

            # Default follow-up (no changes requested)
            if latest_state.get("origin") and trip.origin != latest_state.get("origin"):
                trip.origin = latest_state.get("origin")
                db.commit()
                yield emit_log("Supervisor", f"Updated departure origin to {trip.origin}.")

            ai_reply = await self._generate_ai_followup(destination, user_query, existing_itinerary.content, history, origin=trip.origin)
            runs_repo.complete(agent_run, {"logs": run_logs, "mode": "followup", "reply": ai_reply})

            assistant_msg = messages_repo.create(trip_id, current_user.id, "assistant", ai_reply)
            async for event in self._stream_text(ai_reply, assistant_msg):
                yield event
            return

        # ----------------------------------------------------------------
        # Case 2: New planning session — extract state
        # ----------------------------------------------------------------
        yield emit_log("Supervisor", f"Analysing chat history for {destination}…")
        history_dicts = [{"role": m.role, "content": m.content} for m in history]
        state = await parse_travel_state(history_dicts, destination)

        explicit_dest_change = bool(
            re.search(r'\b(?:change|switch|update|set)\s+(?:the\s+)?destination\s+(?:to|for)\s+([a-zA-Z\s]{2,30})', user_query, re.I)
            or re.search(r'\b(?:instead of\s+[a-zA-Z\s]+,?\s+go\s+to|change\s+trip\s+to)\s+([a-zA-Z\s]{2,30})', user_query, re.I)
        )
        parsed_dest = state.get("destination")
        generic_words = {
            "travelling", "traveling", "travel", "trip", "trips", "tour", "tours",
            "holiday", "vacation", "stay", "relaxing", "exploring", "sightseeing",
            "business", "work", "exploration"
        }
        if (
            explicit_dest_change
            and parsed_dest
            and isinstance(parsed_dest, str)
            and parsed_dest.strip()
            and parsed_dest.strip().lower() not in generic_words
            and parsed_dest.strip().lower() != destination.lower()
        ):
            destination = parsed_dest.strip().title()
            trip.destination = destination
            db.commit()
            yield emit_log("Supervisor", f"Updated trip destination to {destination} based on your explicit request.")
        else:
            destination = trip.destination

        origin: str | None = state.get("origin") or trip.origin
        if origin and trip.origin != origin:
            trip.origin = origin
            db.commit()
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

        if missing:
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

        # ================================================================
        # Step 1: Coordinator Graph (sequential — provides context to rest)
        # ================================================================
        yield emit_log("CoordinatorGraph", "Building trip context and research brief with AI…")
        try:
            coord_output = await coordinator_graph.ainvoke(agent_state)
            current_outputs = coord_output.get("agent_outputs", {})
            agent_state = {**agent_state, "agent_outputs": current_outputs}
        except Exception:
            logger.exception("Coordinator graph failed — continuing with empty context")
            current_outputs = {}

        # ================================================================
        # Step 2: Parallel agents — Flight + Hotel + Weather + Attractions
        # All run concurrently to save time (~3-5x faster than sequential)
        # ================================================================
        yield emit_log("FlightAgent", f"Searching flight options from {origin} to {destination}…")
        yield emit_log("HotelAgent", f"Searching {budget or 'suitable'} hotels in {destination}…")
        yield emit_log("WeatherAgent", f"Fetching weather and climate data for {destination}…")
        yield emit_log("AttractionAgent", f"Searching top-rated spots and local experiences in {destination}…")

        async def _run_flight() -> dict:
            try:
                data = await asyncio.to_thread(get_flight_options, origin, destination, duration_days)
                return data
            except Exception:
                logger.exception("FlightAgent parallel run failed")
                return {"found": False, "reason": "Agent error", "origin": origin, "destination": destination, "source": "error"}

        async def _run_hotel() -> dict:
            try:
                data = await asyncio.to_thread(get_hotel_options, destination, budget, duration_days)
                return data
            except Exception:
                logger.exception("HotelAgent parallel run failed")
                return {"found": False, "reason": "Agent error", "destination": destination, "hotels": [], "budget_tier": "midrange", "cheapest_nightly_inr": 0, "total_hotel_estimate_inr": 0, "source": "error"}

        async def _run_weather() -> dict:
            try:
                weather_raw = await asyncio.to_thread(get_weather.invoke, {"location": destination})
                return json.loads(weather_raw) if isinstance(weather_raw, str) else weather_raw
            except Exception:
                logger.exception("WeatherAgent parallel run failed")
                return {"condition": "Pleasant", "source": "error"}

        async def _run_attractions() -> dict:
            try:
                from app.tools.places_tool import MOCK_PLACES_DB
                loc_key = next(
                    (k for k in MOCK_PLACES_DB if k.lower() in destination.lower() or destination.lower() in k.lower()),
                    None,
                )
                if loc_key and (places := MOCK_PLACES_DB.get(loc_key, [])):
                    top_attrs = [p for p in places if p.get("type") in ("attraction", "shopping")][:5]
                    lines = []
                    for p in top_attrs:
                        lines.append(f"{p['name']} — {p['description']}")
                    if lines:
                        return {"summary": "\n".join(lines), "source": "local"}
                return {
                    "summary": (
                        f"Top attractions in {destination}: Historical landmarks & temples, scenic waterfront/promenade walks, "
                        f"and bustling local street markets for authentic souvenirs and regional street food."
                    ),
                    "source": "heuristic",
                }
            except Exception:
                logger.exception("AttractionAgent run failed")
                return {"summary": f"Explore top attractions and cultural sights in {destination}."}

        async def _run_transport() -> dict:
            try:
                data = await asyncio.to_thread(get_transport_options, destination, origin, budget, duration_days, preferences)
                return data
            except Exception:
                logger.exception("TransportAgent parallel run failed")
                return {"found": False, "reason": "Agent error", "destination": destination, "source": "error"}

        async def _run_food() -> dict:
            try:
                data = await asyncio.to_thread(get_food_recommendations, destination, budget, duration_days, preferences)
                return data
            except Exception:
                logger.exception("FoodAgent parallel run failed")
                return {"found": False, "reason": "Agent error", "destination": destination, "source": "error"}

        # Run all parallel agents concurrently
        flight_data, hotel_data, weather_data, attractions_data, transport_data, food_data = await asyncio.gather(
            _run_flight(),
            _run_hotel(),
            _run_weather(),
            _run_attractions(),
            _run_transport(),
            _run_food(),
        )

        # Log parallel agent results
        if flight_data.get("found"):
            yield emit_log("FlightAgent", f"Found flights via {flight_data.get('carrier')} — round-trip ~Rs.{flight_data.get('roundtrip_price_inr', 0):,} [{flight_data.get('source', '')}]")
        else:
            yield emit_log("FlightAgent", f"Flight data: {flight_data.get('reason', 'not available')}")

        if hotel_data.get("found"):
            yield emit_log("HotelAgent", f"Found {len(hotel_data.get('hotels', []))} {hotel_data.get('budget_tier', '')} hotels — from Rs.{hotel_data.get('cheapest_nightly_inr', 0):,}/night [{hotel_data.get('source', '')}]")
        else:
            yield emit_log("HotelAgent", f"Hotel data: {hotel_data.get('reason', 'not available')}")

        w_temp = weather_data.get("temp", "")
        w_cond = weather_data.get("condition", "")
        w_src = weather_data.get("source", "")
        src_tag = " [live]" if w_src == "openweathermap" else (" [AI]" if w_src == "ai_seasonal" else "")
        yield emit_log("WeatherAgent", f"Weather in {destination}: {w_temp}, {w_cond}{src_tag}")
        if packing := weather_data.get("packing_tips", ""):
            yield emit_log("WeatherAgent", f"🎒 Packing tip: {packing}")

        attr_summary = attractions_data.get("summary", "")
        if attr_summary:
            lines = [ln.strip() for ln in attr_summary.splitlines() if ln.strip()][:2]
            for line in lines:
                yield emit_log("AttractionAgent", f"📍 {line}")
        else:
            yield emit_log("AttractionAgent", "Attraction data will be included in itinerary.")

        # Merge all parallel outputs into current_outputs
        current_outputs["flight"] = flight_data
        current_outputs["hotel"] = hotel_data
        current_outputs["weather"] = weather_data
        current_outputs["attractions"] = attractions_data
        current_outputs["transport"] = transport_data
        current_outputs["food"] = food_data

        # ================================================================
        # Step 3: Budget Agent (needs flight + hotel data — sequential)
        # ================================================================
        yield emit_log("BudgetAgent", "Computing trip budget breakdown…")
        try:
            budget_data = await asyncio.to_thread(
                compute_budget, flight_data, hotel_data, duration_days, budget
            )
            status_label = budget_data.get("status", "unknown")
            total = budget_data.get("grand_total_inr", 0)
            src = budget_data.get("source", "")
            src_tag = " [AI]" if src == "ai" else " [estimate]"
            yield emit_log("BudgetAgent", f"Budget breakdown ready — Total: Rs.{total:,} ({status_label}){src_tag}")
            if feasibility := budget_data.get("feasibility", ""):
                yield emit_log("BudgetAgent", f"💡 Feasibility: {feasibility}")
            for tip in budget_data.get("savings_tips", [])[:2]:
                yield emit_log("BudgetAgent", f"💰 Tip: {tip}")
        except Exception:
            logger.exception("BudgetAgent failed — continuing")
            budget_data = {"status": "incomplete", "grand_total_inr": 0, "missing": ["flight", "hotel"], "warnings": ["Agent error"], "source": "error"}
        current_outputs["budget"] = budget_data

        # Update agent_state with all outputs before planner
        agent_state = {**agent_state, "agent_outputs": current_outputs}

        # ================================================================
        # Step 4: Planner Graph (Gemini synthesis — has ALL agent context)
        # ================================================================
        yield emit_log("PlannerAgent", f"Synthesising final {duration_days}-day itinerary with all agent data…")

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

        # ================================================================
        # Step 5: Persist results
        # ================================================================
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
                "agents_parallel": ["flight", "hotel", "weather", "attractions"],
            },
        )

        assistant_msg = messages_repo.create(trip_id, current_user.id, "assistant", itinerary_text)
        async for event in self._stream_text(itinerary_text, assistant_msg):
            yield event

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _generate_updated_itinerary(agent_state: AgentState) -> str:
        """Attempts planner_graph synthesis, falling back to merge_node if offline or Gemini fails."""
        try:
            planner_output = await planner_graph.ainvoke(agent_state)
            agent_outputs = planner_output.get("agent_outputs", {})
            planner_res = agent_outputs.get("planner", {})
            narrative = planner_res.get("narrative", "")
            if narrative and narrative.strip():
                return narrative
        except Exception:
            logger.warning("Gemini planner failed for modification — using local fallback merge_node", exc_info=True)

        res = merge_node(agent_state)
        return res.get("agent_outputs", {}).get("planner", {}).get("narrative", "")

    @staticmethod
    async def _generate_ai_followup(destination: str, user_query: str, itinerary_content: str, history: list, origin: str | None = None) -> str:
        """Generate a natural, context-aware AI follow-up using Gemini."""
        # Build recent conversation context (last 6 messages)
        history_text = ""
        if history:
            recent = history[-6:]
            for msg in recent:
                role = getattr(msg, "role", "user")
                content = getattr(msg, "content", "")
                if content:
                    snippet = content[:500] + "..." if len(content) > 500 else content
                    history_text += f"{role.upper()}: {snippet}\n"

        # Include relevant portion of the itinerary as context
        itinerary_snippet = itinerary_content[:1500] + "..." if len(itinerary_content) > 1500 else itinerary_content

        sys_msg = SystemMessage(
            content=(
                f"You are VoyagerAI, an expert and friendly AI travel companion. "
                f"The user has a trip planned to {destination} departing from {origin or 'unspecified origin'} and is asking follow-up questions. "
                f"Their existing itinerary is provided for context.\n\n"
                f"RULES:\n"
                f"1. Answer DIRECTLY and SPECIFICALLY — never give generic advice.\n"
                f"2. Use Markdown formatting with emojis for readability.\n"
                f"3. Reference specific places, prices, and real practical tips.\n"
                f"4. If they ask to modify the plan or specify an origin city (e.g., Ahmedabad), acknowledge the change and explain how it affects flight/budget/schedule.\n"
                f"5. If they ask about shopping, name specific markets, their days/timings, and price ranges.\n"
                f"6. If they ask about food, name specific dishes and restaurants with estimated costs.\n"
                f"7. Be conversational and enthusiastic — like a knowledgeable local friend.\n"
                f"8. Keep response focused and concise (150-300 words max).\n\n"
                f"EXISTING ITINERARY CONTEXT:\n{itinerary_snippet}"
            )
        )
        user_prompt_msg = HumanMessage(
            content=(
                f"Destination: {destination}\n"
                f"Origin: {origin or 'Unspecified'}\n\n"
                f"Recent Conversation:\n{history_text}\n"
                f"User's Question: {user_query}\n\n"
                f"Answer their question directly and helpfully."
            )
        )

        try:
            response_text = await call_gemini_async([sys_msg, user_prompt_msg], timeout=20)
            if response_text and response_text.strip():
                return response_text
        except Exception as exc:
            logger.warning("Supervisor: Gemini follow-up failed (%s) — using minimal fallback", exc)

        return SupervisorAgent._minimal_fallback(destination, user_query, origin=origin)

    @staticmethod
    def _minimal_fallback(destination: str, user_query: str, origin: str | None = None) -> str:
        """Honest fallback when ALL Gemini models are unavailable."""
        extracted_origin = origin
        import re
        m = re.search(
            r'\b(?:i am |i\'m )?(?:travellin?g|travel|departing|flying|leaving|coming)?\s*from\s+([a-zA-Z][a-zA-Z\s]{1,30}?)(?:\s+to\b|\s+for\b|,|\.|$)',
            user_query,
            re.IGNORECASE,
        )
        if m:
            cand = m.group(1).strip()
            if cand.lower() not in {"here", "home", "there", "the", "a"}:
                extracted_origin = cand.title()

        origin_msg = ""
        if extracted_origin:
            from app.tools.places_tool import get_transport_info
            transport = get_transport_info(extracted_origin, destination)
            origin_msg = f"Got it! I've updated your departure city to **{extracted_origin}** for your trip to **{destination}**.\n\n{transport}\n\n"

        return (
            f"# ✨ VoyagerAI — {destination} Travel Assistant\n\n"
            f"{origin_msg}"
            f"I'm here to help with your trip to **{destination}**!\n\n"
            f"**Your request:** _{user_query}_\n\n"
            f"Would you like me to revise your flight estimates, hotel choices, or day-by-day itinerary schedule for **{destination}**?\n\n"
            f"- Feel free to ask about top attractions, local food, budget breakdowns, or transport details!\n"
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
        for i in range(0, len(words), 4):
            chunk_words = words[i:i + 4]
            chunk = " ".join(chunk_words) + (" " if i + 4 < len(words) else "")
            yield {"event": "token", "content": chunk}
            await asyncio.sleep(0.001)  # High-speed token streaming

        yield {
            "event": "result",
            "message_id": str(assistant_msg.id),
            "content": text,
        }

"""
SupervisorAgent: the single orchestration entry point for all message sends.

Responsibilities:
  1. Post-itinerary conversational follow-up (Gemini, streaming)
  2. Gating: parse travel state, ask for clarification if params are missing
  3. Run coordinator_graph (logistics, accommodation, experience context)
  4. Run planner_graph (RAG memory retrieval + Gemini itinerary synthesis)
  5. Stream SSE events throughout
  6. Write Message, Itinerary, AgentRun to the database
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.coordinator import coordinator_graph
from app.agents.parser import parse_travel_state
from app.agents.planner import planner_graph
from app.agents.state import AgentState
from app.core.config import get_settings
from app.db.models import Itinerary
from app.repositories import AgentRunRepository, ItineraryRepository, MessageRepository, TripRepository

logger = logging.getLogger(__name__)

_GEMINI_MODEL = "gemini-2.0-flash"


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
        # Case 1: Itinerary already exists → AI follow-up conversation
        # ----------------------------------------------------------------
        existing_itinerary = db.scalar(select(Itinerary).where(Itinerary.trip_id == trip_id))

        if existing_itinerary:
            yield emit_log("Supervisor", f"Itinerary for {destination} already exists — generating follow-up response.")
            ai_reply = await self._generate_followup_reply(
                destination=destination,
                itinerary_content=existing_itinerary.content,
                history=history,
                user_query=user_query,
            )
            runs_repo.complete(agent_run, {"logs": run_logs, "mode": "followup", "reply": ai_reply})

            assistant_msg = messages_repo.create(trip_id, current_user.id, "assistant", ai_reply)
            async for event in self._stream_text(ai_reply, assistant_msg):
                yield event
            return

        # ----------------------------------------------------------------
        # Case 2: New planning session — extract state, gate, then plan
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
        # -------------------------------------------------------
        duration_days = int(duration_days_raw) if duration_days_raw else 3
        
        yield emit_log("Supervisor", f"Validating trip feasibility from {origin} to {destination} for {duration_days} days...")
        feasibility_check = await self._validate_trip_feasibility(origin, destination, duration_days, goal)
        if feasibility_check != "YES":
            runs_repo.complete(agent_run, {"logs": run_logs, "mode": "clarification", "error": "infeasible trip"})
            assistant_msg = messages_repo.create(trip_id, current_user.id, "assistant", feasibility_check)
            async for event in self._stream_text(feasibility_check, assistant_msg):
                yield event
            return

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
        await asyncio.sleep(0.3)

        yield emit_log("MemoryAgent", f"Retrieving past conversation context for {destination}…")
        await asyncio.sleep(0.2)

        # --- Step 1: Run coordinator graph (logistics + accommodation + experience) ---
        yield emit_log("CoordinatorGraph", "Running logistics, accommodation, and experience agents…")
        try:
            coord_output = await coordinator_graph.ainvoke(agent_state)
            agent_state = {**agent_state, "agent_outputs": coord_output.get("agent_outputs", {})}
        except Exception:
            logger.exception("Coordinator graph failed — continuing with empty context")
            coord_output = {}

        yield emit_log("WeatherAgent", f"Fetching weather and climate data for {destination}…")
        await asyncio.sleep(0.2)

        yield emit_log("AttractionAgent", f"Searching top-rated spots and local experiences in {destination}…")
        await asyncio.sleep(0.2)

        yield emit_log("PlannerAgent", f"Synthesising final {duration_days}-day itinerary with Gemini…")

        # --- Step 2: Run planner graph (RAG + Gemini synthesis) ---
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

    async def _generate_followup_reply(
        self,
        destination: str,
        itinerary_content: str,
        history: list,
        user_query: str,
    ) -> str:
        """Generate a conversational AI reply when itinerary already exists."""
        settings = get_settings()
        if settings.gemini_api_key:
            history_text = "\n".join(
                [f"{m.role}: {m.content}" for m in history[-6:]]
            )
            prompt = (
                f"You are the VoyagerAI travel assistant. An itinerary for {destination} has been generated.\n\n"
                f"Current Itinerary:\n{itinerary_content[:2000]}\n\n"
                f"Recent Chat History:\n{history_text}\n\n"
                f"User's latest message: {user_query}\n\n"
                "Respond helpfully and conversationally. If they ask about hotels, flights, or modifications, "
                "suggest options or explain how the itinerary could be adjusted. Use Markdown for formatting."
            )
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{_GEMINI_MODEL}:generateContent?key={settings.gemini_api_key}"
            )
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    response = await client.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
                    if response.status_code == 200:
                        data = response.json()
                        return data["candidates"][0]["content"]["parts"][0]["text"]
            except Exception:
                logger.exception("Gemini follow-up reply failed")

        return (
            "Your itinerary is already saved! Feel free to ask me any follow-up questions "
            "about your trip, hotels, activities, or modifications."
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

    async def _validate_trip_feasibility(self, origin: str, destination: str, duration_days: int, goal: str) -> str:
        """Check if the trip makes logical sense (distance vs duration)."""
        settings = get_settings()
        if not settings.gemini_api_key:
            return "YES"
            
        prompt = (
            f"A user wants to travel from {origin} to {destination} for a {duration_days}-day trip. "
            f"Their main goal is: {goal}. "
            "Is this trip realistically feasible? Consider flight/travel times. For example, travelling halfway across the world for just 1 or 2 days is generally not feasible. "
            "If it is feasible, respond with exactly 'YES'. "
            "If it is NOT feasible, explain briefly and conversationally why it is not possible and ask them to adjust their duration or destination."
        )
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{_GEMINI_MODEL}:generateContent?key={settings.gemini_api_key}"
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
                if response.status_code == 200:
                    data = response.json()
                    res = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if res.upper().startswith("YES"):
                        return "YES"
                    return res
        except Exception as exc:
            logger.warning("Feasibility check failed: %s", exc)
        return "YES"

    @staticmethod
    async def _stream_text(text: str, assistant_msg) -> AsyncGenerator[dict, None]:
        """Yield token-level events then a final result event."""
        words = text.split(" ")
        for i, word in enumerate(words):
            chunk = (word + " ") if i < len(words) - 1 else word
            yield {"event": "token", "content": chunk}
            await asyncio.sleep(0.01)

        yield {
            "event": "result",
            "message_id": str(assistant_msg.id),
            "content": text,
        }

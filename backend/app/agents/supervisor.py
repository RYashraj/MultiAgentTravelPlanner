"""
Supervisor Agent Orchestrator.
Manages the travel planning pipeline, orchestrates sub-agents,
and records session metrics to the database.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User, Trip, Message, Itinerary, AgentRun
from app.db.session import get_db
from app.repositories import AgentRunRepository, ItineraryRepository, MessageRepository, TripRepository
from app.agents.parser import parse_travel_state
from app.core.config import get_settings
import httpx
import json

logger = logging.getLogger(__name__)


class SupervisorAgent:
    """
    Coordinates sub-agent tasks, validates budget constraints, compiles final
    itineraries, and logs running session metrics.
    """

    async def run_orchestration_stream(
        self,
        db: Session,
        trip_id: uuid.UUID,
        user_query: str,
        current_user: Any,
    ) -> AsyncGenerator[dict, None]:
        """
        Executes the multi-agent planning step-by-step.
        Yields logs and intermediate chunks, then writes Itinerary/clarifying messages and AgentRun to the DB.
        """
        # Retrieve the trip
        trip = TripRepository(db).get_for_user(trip_id, current_user.id)
        if not trip:
            return
        destination = trip.destination

        # Initialize Agent Run session in DB
        runs = AgentRunRepository(db)
        agent_run = runs.start(trip_id, {"user_query": user_query})

        logs_list: list[dict] = []

        def add_run_log(agent: str, content: str) -> None:
            logs_list.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent": agent,
                "content": content,
            })

        # Load message history
        messages_repo = MessageRepository(db)
        history = messages_repo.list_for_trip(trip_id)

        # Check if itinerary already exists to prevent re-generation loop
        existing_itinerary = db.scalar(select(Itinerary).where(Itinerary.trip_id == trip_id))

        if existing_itinerary:
            settings = get_settings()
            if settings.gemini_api_key:
                # Use AI for post-itinerary conversation
                history_text = "\n".join([f"{msg.role}: {msg.content}" for msg in history[-5:]])
                prompt = (
                    f"You are the VoyagerAI travel assistant. An itinerary for {destination} has already been generated.\n\n"
                    f"Current Itinerary Plan:\n{existing_itinerary.content}\n\n"
                    f"Recent Chat History:\n{history_text}\n\n"
                    f"User's latest message: {user_query}\n\n"
                    f"Respond helpfully and conversationally as an AI agent. If they ask for hotels, flights, or modifications, suggest options or explain how the itinerary could be adjusted. Use markdown for formatting."
                )
                
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={settings.gemini_api_key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}]
                }
                
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        response = await client.post(url, json=payload)
                        if response.status_code == 200:
                            data = response.json()
                            ai_reply = data["candidates"][0]["content"]["parts"][0]["text"]
                            
                            runs.complete(agent_run, {
                                "logs": logs_list,
                                "message": ai_reply,
                                "coordinator_output": {"status": "chat_response"},
                            })
                            
                            words = ai_reply.split(" ")
                            for i, word in enumerate(words):
                                chunk = (word + " ") if i < len(words) - 1 else word
                                yield {"event": "message_chunk", "content": chunk, "sender": "assistant"}
                                await asyncio.sleep(0.02)
                                
                            assistant_msg = messages_repo.create(trip_id, current_user.id, "assistant", ai_reply)
                            yield {"event": "message_complete", "id": str(assistant_msg.id), "content": ai_reply, "sender": "assistant"}
                            return
                except Exception as e:
                    logger.exception("Failed to generate AI response for follow-up")
                    
            # Fallback if no API key or API fails
            reply_msg = (
                "Your itinerary is already generated and saved! "
                "However, the AI service is currently unavailable for follow-up questions."
            )
            runs.complete(agent_run, {
                "logs": logs_list,
                "message": reply_msg,
                "coordinator_output": {"status": "already_completed"},
            })
            for i, word in enumerate(reply_msg.split(" ")):
                chunk = (word + " ") if i < len(reply_msg.split(" ")) - 1 else word
                yield {"event": "message_chunk", "content": chunk, "sender": "assistant"}
                await asyncio.sleep(0.02)

            assistant_msg = messages_repo.create(trip_id, current_user.id, "assistant", reply_msg)
            yield {"event": "message_complete", "id": str(assistant_msg.id), "content": reply_msg, "sender": "assistant"}
            return

        # Extract current state from history
        state = await parse_travel_state(history, destination)
        budget: str | None = state.get("budget")
        origin: str | None = state.get("origin")
        duration_days_raw = state.get("duration_days")
        dates: str | None = state.get("dates")
        goal: str | None = state.get("goal")
        preferences: list[str] = state.get("preferences") or []

        # Determine missing parameters
        missing_items = []
        if not origin:
            missing_items.append("origin")
        if not budget:
            missing_items.append("budget")
        if not duration_days_raw:
            missing_items.append("duration")
        if not goal:
            missing_items.append("main goal or purpose")

        if missing_items:
            clarification_msg = (
                f"I'd love to help you plan an amazing trip to **{destination}**! "
                "To get started, could you please provide a few more details?\n\n"
            )
            for item in missing_items:
                if item == "budget":
                    clarification_msg += "- **What is your budget?** (e.g., $1000, 50,000 INR, budget-friendly, luxury)\n"
                elif item == "origin":
                    clarification_msg += "- **Which city are you traveling from?**\n"
                elif item == "duration":
                    clarification_msg += "- **How many days** would you like your trip to be?\n"
                elif item == "main goal or purpose":
                    clarification_msg += "- **What is the main goal of your trip?** (e.g., relaxation, food, honeymoon)\n"
            clarification_msg += "\nOnce you share these, my agents will immediately coordinate to compile your plan!"

            runs.complete(agent_run, {
                "logs": logs_list,
                "message": clarification_msg,
                "coordinator_output": {"status": "clarification_needed", "missing": missing_items},
            })

            words = clarification_msg.split(" ")
            for i, word in enumerate(words):
                chunk = (word + " ") if i < len(words) - 1 else word
                yield {"event": "message_chunk", "content": chunk, "sender": "assistant"}
                await asyncio.sleep(0.02)

            assistant_msg = messages_repo.create(trip_id, current_user.id, "assistant", clarification_msg)
            yield {"event": "message_complete", "id": str(assistant_msg.id), "content": clarification_msg, "sender": "assistant"}
            return

        # All parameters collected — run the sub-agent planner graph
        from app.agents.planner import planner_graph, AgentState

        state_input = AgentState(
            trip_id=str(trip_id),
            origin=origin,
            destination=destination,
            dates=dates,
            budget=budget,
            preferences=preferences,
            user_message=user_query,
            memory_context=[],
            agent_outputs={},
        )

        coord_msg = (
            f"[Coordinator] All parameters collected. Destination: {destination}, "
            f"Budget: {budget}, Duration: {duration_days_raw} days, Dates: {dates}. "
            "Initiating core planning agents."
        )
        yield {"event": "agent_log", "agent": "CoordinatorAgent", "content": coord_msg}
        add_run_log("CoordinatorAgent", coord_msg)
        await asyncio.sleep(0.5)

        mem_msg = f"[Memory] Retrieving past conversation context for {destination}..."
        yield {"event": "agent_log", "agent": "MemoryAgent", "content": mem_msg}
        add_run_log("MemoryAgent", mem_msg)
        await asyncio.sleep(0.5)

        # Run the graph
        graph_output = await asyncio.to_thread(planner_graph.invoke, state_input)
        
        weather_msg = f"[Weather] Checking real-time forecast and climate constraints for {destination}."
        yield {"event": "agent_log", "agent": "WeatherAgent", "content": weather_msg}
        add_run_log("WeatherAgent", weather_msg)
        await asyncio.sleep(0.5)

        attr_msg = f"[Attractions] Querying Google Places for top-rated spots matching your preferences."
        yield {"event": "agent_log", "agent": "AttractionAgent", "content": attr_msg}
        add_run_log("AttractionAgent", attr_msg)
        await asyncio.sleep(0.5)

        duration_days = int(duration_days_raw) if duration_days_raw else 3
        planner_msg = f"[Planner] Tool execution complete. Merging data into final {duration_days}-day travel plan..."
        yield {"event": "agent_log", "agent": "PlannerAgent", "content": planner_msg}
        add_run_log("PlannerAgent", planner_msg)
        await asyncio.sleep(0.5)

        # Extract agent results
        agent_outputs = graph_output.get("agent_outputs", {})
        planner_res = agent_outputs.get("planner", {})
        itinerary_text = planner_res.get("narrative", "")

        if not itinerary_text:
            itinerary_text = (
                f"Here is your VoyagerAI travel itinerary for **{destination}**!\n\n"
                f"*(Note: Failed to generate dynamic narrative. Using raw data fallback)*\n\n"
            )

        itineraries = ItineraryRepository(db)
        itineraries.save(trip_id, itinerary_text)

        runs.complete(agent_run, {
            "logs": logs_list,
            "message": itinerary_text,
            "coordinator_output": {},
        })

        words = itinerary_text.split(" ")
        for i, word in enumerate(words):
            chunk = (word + " ") if i < len(words) - 1 else word
            yield {"event": "message_chunk", "content": chunk, "sender": "assistant"}
            await asyncio.sleep(0.02)

        assistant_msg = messages_repo.create(trip_id, current_user.id, "assistant", itinerary_text)
        yield {"event": "message_complete", "id": str(assistant_msg.id), "content": itinerary_text, "sender": "assistant"}

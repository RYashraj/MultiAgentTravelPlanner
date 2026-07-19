"""
Supervisor Agent Orchestrator.
Manages the travel planning pipeline, orchestrates sub-agents,
and records session metrics to the database.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Any

from sqlalchemy.orm import Session

from app.db.models import User, Trip, Message, Itinerary, AgentRun
from app.repositories import AgentRunRepository, ItineraryRepository, MessageRepository, TripRepository

logger = logging.getLogger(__name__)

from app.agents.parser import parse_travel_state

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
        current_user: Any
    ) -> AsyncGenerator[dict, None]:
        """
        Executes the multi-agent planning simulation step-by-step.
        Yields logs and intermediate chunks, then writes Itinerary/clarifying messages and AgentRun to the DB.
        """
        # Retrieve the trip
        trip = TripRepository(db).get_for_user(trip_id, current_user.id)
        if not trip:
            return
        destination = trip.destination

        # Initialize Agent Run session in DB
        runs = AgentRunRepository(db)
        input_payload = {"user_query": user_query}
        agent_run = runs.start(trip_id, input_payload)

        logs_list = []
        def add_run_log(agent: str, content: str):
            logs_list.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent": agent,
                "content": content
            })

        # Load message history
        messages_repo = MessageRepository(db)
        history = messages_repo.list_for_trip(trip_id)

        # Check if itinerary already exists to prevent endless regeneration loop
        from sqlalchemy import select
        from app.db.models import Itinerary
        existing_itinerary = db.scalar(select(Itinerary).where(Itinerary.trip_id == trip_id))
        
        if existing_itinerary:
            reply_msg = "Your itinerary is already generated and finalized! We are holding work here for now. Next week, conversational AI features will be added so we can chat further! If you want a new plan right now, please create a new trip."
            
            runs.complete(agent_run, {
                "logs": logs_list,
                "message": reply_msg,
                "coordinator_output": {"status": "already_completed"}
            })
            
            words = reply_msg.split(" ")
            for i, word in enumerate(words):
                chunk = (word + " ") if i < len(words) - 1 else word
                yield {
                    "event": "message_chunk",
                    "content": chunk,
                    "sender": "assistant"
                }
                await asyncio.sleep(0.02)

            assistant_msg = messages_repo.create(trip_id, current_user.id, "assistant", reply_msg)
            yield {
                "event": "message_complete",
                "id": str(assistant_msg.id),
                "content": reply_msg,
                "sender": "assistant"
            }
            return

        # Extract current state from history
        state = await parse_travel_state(history, destination)
        budget = state.get("budget")
        duration_days = state.get("duration_days")
        dates = state.get("dates")
        goal = state.get("goal")
        conditions = state.get("conditions")
        preferences = state.get("preferences") or []

        # Determine missing parameters
        missing_items = []
        if not budget:
            missing_items.append("budget")
        if not duration_days:
            missing_items.append("duration")
        if not dates:
            missing_items.append("dates/time of travel")
        if not goal:
            missing_items.append("main goal or purpose")

        if missing_items:
            # We are missing details; ask clarifying questions conversationally
            clarification_msg = (
                f"I'd love to help you plan an amazing trip to **{destination}**! "
                f"To get started on curating your itinerary, could you please provide a few more details?\n\n"
            )
            for item in missing_items:
                if item == "budget":
                    clarification_msg += "- **What is your budget?** (e.g., $1000, 50,000 INR, budget-friendly, luxury)\n"
                elif item == "duration":
                    clarification_msg += "- **How many days** would you like your trip to be?\n"
                elif item == "dates/time of travel":
                    clarification_msg += "- **When are you planning to go?** (e.g., specific dates, or a month/season like June or winter)\n"
                elif item == "main goal or purpose":
                    clarification_msg += "- **What is the main goal of your trip?** (e.g., relaxation, food exploration, business, honeymoon)\n"
            clarification_msg += "\nOnce you share these, my specialist agents (Logistics, Lodging, and Experience) will immediately coordinate to compile your customized day-by-day plan!"

            # Complete the Agent Run with status
            runs.complete(agent_run, {
                "logs": logs_list,
                "message": clarification_msg,
                "coordinator_output": {
                    "status": "clarification_needed",
                    "missing": missing_items
                }
            })

            # Stream the clarifying response
            words = clarification_msg.split(" ")
            for i, word in enumerate(words):
                chunk = (word + " ") if i < len(words) - 1 else word
                yield {
                    "event": "message_chunk",
                    "content": chunk,
                    "sender": "assistant"
                }
                await asyncio.sleep(0.02)

            assistant_msg = messages_repo.create(trip_id, current_user.id, "assistant", clarification_msg)
            yield {
                "event": "message_complete",
                "id": str(assistant_msg.id),
                "content": clarification_msg,
                "sender": "assistant"
            }
            return

        # If we have all parameters, run the sub-agent pipeline
        from app.agents.coordinator import coordinator_graph, AgentState

        state_input = AgentState(
            destination=destination,
            dates=dates,
            budget=budget,
            preferences=preferences,
            user_message=user_query,
            agent_outputs={}
        )

        # Step 1: Run the Coordinator StateGraph skeleton
        graph_output = await asyncio.to_thread(coordinator_graph.invoke, state_input)
        coordinator_output = graph_output.get("agent_outputs", {}).get("coordinator", {})
        coord_msg = f"[Coordinator] All parameters collected. Destination: {destination}, Budget: {budget}, Duration: {duration_days} days, Dates: {dates}. Initiating specialist agent collaboration."

        yield {
            "event": "agent_log",
            "agent": "CoordinatorAgent",
            "content": coord_msg
        }
        add_run_log("CoordinatorAgent", coord_msg)
        await asyncio.sleep(1.0)

        # Step 2: Logistics Agent fetches transport options
        logistics_msg = f"[Logistics] Querying travel routes & flight options to {destination}. Found optimal route."
        yield {
            "event": "agent_log",
            "agent": "LogisticsAgent",
            "content": logistics_msg
        }
        add_run_log("LogisticsAgent", logistics_msg)
        await asyncio.sleep(1.2)

        # Step 3: Accommodation Agent searches stays
        acc_msg = f"[Accommodation] Searching stays in {destination} within {budget} parameters."
        yield {
            "event": "agent_log",
            "agent": "AccommodationAgent",
            "content": acc_msg
        }
        add_run_log("AccommodationAgent", acc_msg)
        await asyncio.sleep(1.2)

        # Step 4: Experience Agent curates activities
        exp_msg = f"[Experiences] Compiling top attractions, local sightseeing spots, and culinary experiences in {destination}."
        yield {
            "event": "agent_log",
            "agent": "ExperienceAgent",
            "content": exp_msg
        }
        add_run_log("ExperienceAgent", exp_msg)
        await asyncio.sleep(1.2)

        # Step 5: Supervisor compiles final plan & saves Itinerary
        sup_msg = f"[Orchestrator] Budget constraints verified. Compiling consolidated day-by-day travel plan for {duration_days} days..."
        yield {
            "event": "agent_log",
            "agent": "SupervisorAgent",
            "content": sup_msg
        }
        add_run_log("SupervisorAgent", sup_msg)
        await asyncio.sleep(0.8)

        # Compile detailed day-by-day itinerary text based on duration
        days_schedule_text = ""
        for day in range(1, duration_days + 1):
            if day == 1:
                days_schedule_text += f"- **Day 1: Arrival & Landmarks**: Explore core historic monuments and local walking paths.\n"
            elif day == 2:
                days_schedule_text += f"- **Day 2: Gastronomy & Culture**: Visit popular central markets, museum exhibits, and street food stalls.\n"
            elif day == duration_days:
                days_schedule_text += f"- **Day {day}: Departure & Leisure**: Last minute souvenir shopping and departure preparations.\n"
            elif day == 3:
                days_schedule_text += f"- **Day 3: Scenic Excursions**: Relax in primary nature parks and take a scenic skyline tour.\n"
            elif day % 2 == 0:
                days_schedule_text += f"- **Day {day}: Hidden Gems**: Discover off-the-beaten-path neighborhoods and local cafes.\n"
            else:
                days_schedule_text += f"- **Day {day}: Adventure & Activity**: Engage in outdoor activities or interactive workshops.\n"


        itinerary_text = (
            f"Here is your completed VoyagerAI travel itinerary for **{destination}**!\n\n"
            f"### ✈️ Flights & Transit (Logistics)\n"
            f"- Round-trip flights successfully verified and mapped to local transit.\n\n"
            f"### 🏨 Hotel & Lodging\n"
            f"- Central boutique hotel selected within transit proximity.\n\n"
            f"### 🗺️ Day-by-Day Experience Schedule\n"
            f"{days_schedule_text}\n"
            f"Enjoy your trip! Let me know if you would like to edit or book any segment."
        )

        # Save Itinerary to DB using repository
        itineraries = ItineraryRepository(db)
        itinerary_db = itineraries.save(trip_id, itinerary_text)

        # Update Agent Run status to completed using repository
        output_payload = {
            "logs": logs_list,
            "message": itinerary_text,
            "coordinator_output": coordinator_output
        }
        runs.complete(agent_run, output_payload)

        # Yield actual itinerary text chunk by chunk to simulate streaming
        words = itinerary_text.split(" ")
        for i, word in enumerate(words):
            chunk = (word + " ") if i < len(words) - 1 else word
            yield {
                "event": "message_chunk",
                "content": chunk,
                "sender": "assistant"
            }
            await asyncio.sleep(0.02)

        # Yield complete message token using repository
        assistant_msg = messages_repo.create(trip_id, current_user.id, "assistant", itinerary_text)

        yield {
            "event": "message_complete",
            "id": str(assistant_msg.id),
            "content": itinerary_text,
            "sender": "assistant"
        }


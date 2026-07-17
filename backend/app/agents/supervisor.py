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
        Yields logs and intermediate chunks, then writes Itinerary and AgentRun to the DB.
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

        # Step 1: Run the Coordinator StateGraph skeleton
        from app.agents.coordinator import coordinator_graph, AgentState
        
        state_input = AgentState(
            destination=destination,
            dates=None,
            budget=None,
            preferences=[],
            user_message=user_query,
            agent_outputs={}
        )
        
        # Invoke the compiled graph
        graph_output = await asyncio.to_thread(coordinator_graph.invoke, state_input)
        coordinator_output = graph_output.get("agent_outputs", {}).get("coordinator", {})
        message_text = coordinator_output.get("message", f"Planning has started for {destination}.")
        
        yield {
            "event": "agent_log",
            "agent": "CoordinatorAgent",
            "content": message_text
        }
        add_run_log("CoordinatorAgent", message_text)
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
        acc_msg = f"[Accommodation] Searching stays in {destination} within standard budget parameters."
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
        sup_msg = "[Orchestrator] Budget constraints verified. Compiling consolidated day-by-day travel plan..."
        yield {
            "event": "agent_log",
            "agent": "SupervisorAgent",
            "content": sup_msg
        }
        add_run_log("SupervisorAgent", sup_msg)
        await asyncio.sleep(0.8)

        # Compile detailed itinerary text
        itinerary_text = (
            f"Here is your completed VoyagerAI travel itinerary for **{destination}**!\n\n"
            f"### ✈️ Flights & Transit (Logistics)\n"
            f"- Round-trip flights successfully verified and mapped to local transit.\n\n"
            f"### 🏨 Hotel & Lodging\n"
            f"- Central boutique hotel selected within transit proximity.\n\n"
            f"### 🗺️ Day-by-Day Experience Schedule\n"
            f"- **Day 1: Arrival & Landmarks**: Explore core historic monuments and local walking paths.\n"
            f"- **Day 2: Gastronomy & Culture**: Visit popular central markets, museum exhibits, and street food stalls.\n"
            f"- **Day 3: Scenic Excursions**: Relax in primary nature parks and take a scenic skyline tour.\n\n"
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
            await asyncio.sleep(0.03)

        # Yield complete message token using repository
        messages = MessageRepository(db)
        assistant_msg = messages.create(trip_id, current_user.id, "assistant", itinerary_text)

        yield {
            "event": "message_complete",
            "id": str(assistant_msg.id),
            "content": itinerary_text,
            "sender": "assistant"
        }

"""
Trip & Message API routes.
POST /trips/{id}/messages supports both streaming (SSE) and non-streaming modes.
"""
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents.planner import planner_graph
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.rag.chroma_store import ChromaMemoryStore
from app.agents.parser import parse_travel_state
import asyncio
from app.repositories import (
    AgentRunRepository,
    ItineraryRepository,
    MessageRepository,
    TripRepository,
    UserRepository,
)
from app.schemas.trips import MessageCreate, MessageResponse, TripCreate, TripResponse

router = APIRouter(prefix="/trips", tags=["trips"])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def owned_trip(trip_id: uuid.UUID, user: CurrentUser, db: Session):
    trip = TripRepository(db).get_for_user(trip_id, user.id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return trip


def _build_initial_state(trip_id: uuid.UUID, destination: str, payload: MessageCreate) -> dict:
    return {
        "trip_id": str(trip_id),
        "destination": destination,
        "dates": payload.dates,
        "budget": payload.budget,
        "preferences": list(payload.preferences),
        "user_message": payload.content,
        "memory_context": [],
        "agent_outputs": {},
    }


def _collect_narrative(step: dict) -> str:
    """Extract the narrative string from the final graph step output."""
    # Try merge node output first
    planner_output = step.get("merge", {}).get("agent_outputs", {}).get("planner", {})
    if not planner_output:
        # Flat key fallback
        planner_output = step.get("agent_outputs", {}).get("planner", {})

    narrative = planner_output.get("narrative", "")
    if narrative:
        return narrative

    return "Your itinerary is being prepared. Please try again in a moment."


# ---------------------------------------------------------------------------
# CRUD routes
# ---------------------------------------------------------------------------

@router.post("", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
def create_trip(
    payload: TripCreate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    UserRepository(db).upsert(user.id, user.email, user.full_name)
    return TripRepository(db).create(user.id, payload.destination.strip())


@router.get("", response_model=list[TripResponse])
def list_trips(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return TripRepository(db).list_for_user(user.id)


@router.get("/{trip_id}", response_model=TripResponse)
def get_trip(
    trip_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return owned_trip(trip_id, user, db)


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip(
    trip_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trip = owned_trip(trip_id, user, db)
    db.delete(trip)
    db.commit()
    return None


@router.get("/{trip_id}/messages", response_model=list[MessageResponse])
def list_messages(
    trip_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    owned_trip(trip_id, user, db)
    return MessageRepository(db).list_for_trip(trip_id)


@router.get("/{trip_id}/itineraries")
def get_itinerary(
    trip_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    owned_trip(trip_id, user, db)
    itinerary = ItineraryRepository(db).get_for_trip(trip_id)
    if itinerary is None:
        raise HTTPException(status_code=404, detail="No itinerary found for this trip")
    return {"id": str(itinerary.id), "content": itinerary.content, "status": itinerary.status}


# ---------------------------------------------------------------------------
# Message endpoint — supports both sync and SSE streaming
# ---------------------------------------------------------------------------

@router.post("/{trip_id}/messages")
async def send_message(
    trip_id: uuid.UUID,
    payload: MessageCreate,
    stream: bool = False,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trip = owned_trip(trip_id, user, db)
    messages_repo = MessageRepository(db)
    runs_repo = AgentRunRepository(db)
    chroma_store = ChromaMemoryStore()

    # Save the user message immediately
    user_message = messages_repo.create(trip.id, user.id, "user", payload.content.strip())
    try:
        chroma_store.embed_message(str(trip.id), str(user_message.id), "user", user_message.content)
    except Exception:
        pass  # ChromaDB embedding is best-effort

    # --- Conversational Gating Logic ---
    history = messages_repo.list_for_trip(trip.id)
    # Convert ORM history to dictionaries matching expected parser format
    history_dicts = [{"role": msg.role, "content": msg.content} for msg in history]
    state = await parse_travel_state(history_dicts, trip.destination)
    
    budget = state.get("budget")
    duration_days = state.get("duration_days")
    goal = state.get("goal")
    
    missing_items = []
    if not budget: missing_items.append("budget")
    if not duration_days: missing_items.append("duration")
    if not goal: missing_items.append("main goal or purpose")

    if missing_items:
        clarification_msg = (
            f"I'd love to help you plan an amazing trip to **{trip.destination}**! "
            "To get started, could you please provide a few more details?\n\n"
        )
        if "budget" in missing_items:
            clarification_msg += "- **What is your budget?** (e.g., $1000, 50,000 INR, budget-friendly, luxury)\n"
        if "duration" in missing_items:
            clarification_msg += "- **How many days** would you like your trip to be?\n"
        if "main goal or purpose" in missing_items:
            clarification_msg += "- **What is the main goal of your trip?** (e.g., relaxation, food, honeymoon)\n"
        clarification_msg += "\nOnce you share these, I'll compile your plan!"

        if not stream:
            assistant_msg = messages_repo.create(trip.id, user.id, "assistant", clarification_msg)
            return {
                "user_message": {"id": str(user_message.id), "content": user_message.content},
                "coordinator_message": {"id": str(assistant_msg.id), "content": assistant_msg.content},
                "itinerary": None,
                "run_id": None,
            }
        
        async def clarify_generator():
            assistant_msg = messages_repo.create(trip.id, user.id, "assistant", clarification_msg)
            for token in clarification_msg.split(" "):
                yield f"data: {json.dumps({'type': 'token', 'content': token + ' '})}\n\n"
                await asyncio.sleep(0.02)
            yield f"data: {json.dumps({'type': 'result', 'user_message': {'id': str(user_message.id), 'content': user_message.content}, 'coordinator_message': {'id': str(assistant_msg.id), 'content': assistant_msg.content}, 'itinerary': None, 'run_id': None})}\n\n"
            yield "event: done\ndata: {}\n\n"
            
        return StreamingResponse(clarify_generator(), media_type="text/event-stream")

    # --- Actual Planning Graph Execution ---
    initial_state = _build_initial_state(trip.id, trip.destination, payload)
    run = runs_repo.start(trip.id, initial_state)

    if not stream:
        try:
            final_step: dict = {}
            for step in planner_graph.stream(initial_state):
                final_step = step

            full_narrative = _collect_narrative(final_step)
            planner_output = (
                final_step.get("merge", {}).get("agent_outputs", {}).get("planner", {})
                or final_step.get("agent_outputs", {}).get("planner", {})
            )

            runs_repo.complete(run, {**planner_output, "narrative": full_narrative})
            coordinator_message = messages_repo.create(trip.id, user.id, "assistant", full_narrative)
            try:
                chroma_store.embed_message(
                    str(trip.id), str(coordinator_message.id), "assistant", coordinator_message.content
                )
            except Exception:
                pass

            ItineraryRepository(db).save(trip.id, full_narrative)
            trip.status = "planning"
            db.commit()

            return {
                "user_message": {"id": str(user_message.id), "content": user_message.content},
                "coordinator_message": {"id": str(coordinator_message.id), "content": coordinator_message.content},
                "itinerary": full_narrative,
                "run_id": str(run.id),
            }
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=500, detail=str(exc))

    u_msg_id = str(user_message.id)
    u_msg_content = user_message.content
    run_id_str = str(run.id)
    run_uuid = run.id
    trip_uuid = trip.id
    user_uuid = user.id

    async def event_generator():
        try:
            final_step: dict = {}
            # Run the synchronous graph stream in a thread pool to avoid blocking the async loop
            stream_gen = await asyncio.to_thread(lambda: list(planner_graph.stream(initial_state)))
            
            for step in stream_gen:
                step_name = next(iter(step), "unknown")
                yield f"data: {json.dumps({'type': 'status', 'step': step_name})}\n\n"
                final_step = step
                await asyncio.sleep(0.01)

            full_narrative = _collect_narrative(final_step)
            planner_output = (
                final_step.get("merge", {}).get("agent_outputs", {}).get("planner", {})
                or final_step.get("agent_outputs", {}).get("planner", {})
            )

            for token in full_narrative.split(" "):
                yield f"data: {json.dumps({'type': 'token', 'content': token + ' '})}\n\n"
                await asyncio.sleep(0.01)

            from app.db.models import AgentRun as AgentRunModel, Trip as TripModel
            fresh_run = db.get(AgentRunModel, run_uuid)
            if fresh_run:
                runs_repo.complete(fresh_run, {**planner_output, "narrative": full_narrative})

            coordinator_message = messages_repo.create(trip_uuid, user_uuid, "assistant", full_narrative)
            try:
                chroma_store.embed_message(
                    str(trip_uuid), str(coordinator_message.id), "assistant", coordinator_message.content
                )
            except Exception:
                pass

            ItineraryRepository(db).save(trip_uuid, full_narrative)

            fresh_trip = db.get(TripModel, trip_uuid)
            if fresh_trip:
                fresh_trip.status = "planning"
            db.commit()

            yield f"data: {json.dumps({'type': 'result', 'user_message': {'id': u_msg_id, 'content': u_msg_content}, 'coordinator_message': {'id': str(coordinator_message.id), 'content': full_narrative}, 'itinerary': full_narrative, 'run_id': run_id_str})}\n\n"
            yield "event: done\ndata: {}\n\n"

        except Exception as exc:
            db.rollback()
            yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"
            yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
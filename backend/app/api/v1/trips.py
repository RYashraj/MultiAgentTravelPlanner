"""
Trip & Message API routes.

The send_message endpoint delegates all business logic to SupervisorAgent.
This file is purely an HTTP adapter — no planning logic lives here.
"""
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents.supervisor import SupervisorAgent
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.repositories import (
    ItineraryRepository,
    MessageRepository,
    TripRepository,
    UserRepository,
)
from app.schemas.trips import MessageCreate, MessageResponse, TripCreate, TripResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trips", tags=["trips"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _owned_trip(trip_id: uuid.UUID, user: CurrentUser, db: Session):
    trip = TripRepository(db).get_for_user(trip_id, user.id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return trip


def _embed_message_best_effort(trip_id: uuid.UUID, message_id: uuid.UUID, role: str, content: str) -> None:
    """Best-effort ChromaDB embedding — failures are silently logged, never raised."""
    try:
        from app.agents.planner import _get_chroma_store
        store = _get_chroma_store()
        if store:
            store.embed_message(str(trip_id), str(message_id), role, content)
    except Exception as exc:
        logger.debug("Chroma embed skipped: %s", exc)


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
def list_trips(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return TripRepository(db).list_for_user(user.id)


@router.get("/{trip_id}", response_model=TripResponse)
def get_trip(
    trip_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _owned_trip(trip_id, user, db)


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip(
    trip_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trip = _owned_trip(trip_id, user, db)
    try:
        db.delete(trip)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to delete trip %s", trip_id)
        raise HTTPException(status_code=500, detail="Failed to delete trip")


@router.get("/{trip_id}/messages", response_model=list[MessageResponse])
def list_messages(
    trip_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trip = _owned_trip(trip_id, user, db)
    msgs = MessageRepository(db).list_for_trip(trip_id)
    if not msgs:
        welcome_msg = (
            f"Hello! Let's plan your **{trip.destination}** trip! ✈️\n\n"
            f"Tell me your travel details:\n"
            f"- **Where** are you travelling from?\n"
            f"- **How many days** would you like to stay?\n"
            f"- **What is your budget** (e.g., ₹50,000, mid-range, luxury)?\n"
            f"- **What is your main goal** (e.g., shopping, sightseeing, relaxation)?"
        )
        created = MessageRepository(db).create(trip.id, user.id, "assistant", welcome_msg)
        return [created]
    return msgs


@router.get("/{trip_id}/itineraries")
def get_itinerary(
    trip_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _owned_trip(trip_id, user, db)
    itinerary = ItineraryRepository(db).get_for_trip(trip_id)
    if itinerary is None:
        raise HTTPException(status_code=404, detail="No itinerary found for this trip")
    return {
        "id": str(itinerary.id),
        "content": itinerary.content,
        "status": itinerary.status,
        "created_at": itinerary.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Message endpoint — delegates to SupervisorAgent
# ---------------------------------------------------------------------------

@router.post("/{trip_id}/messages")
async def send_message(
    trip_id: uuid.UUID,
    payload: MessageCreate,
    stream: bool = True,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Send a message and receive an AI response.

    ?stream=true  (default) — returns a Server-Sent Events stream.
    ?stream=false            — collects all events and returns a single JSON response.
    """
    trip = _owned_trip(trip_id, user, db)
    messages_repo = MessageRepository(db)

    # Persist the user message immediately
    user_msg = messages_repo.create(trip.id, user.id, "user", payload.content.strip())
    _embed_message_best_effort(trip.id, user_msg.id, "user", user_msg.content)

    agent = SupervisorAgent()

    if not stream:
        # Collect all SSE events and return a single JSON response
        try:
            final_content = ""
            final_message_id = ""
            async for event in agent.run_orchestration_stream(db, trip_id, payload.content.strip(), user):
                if event.get("event") == "result":
                    final_content = event.get("content", "")
                    final_message_id = event.get("message_id", "")
                elif event.get("event") == "error":
                    raise HTTPException(status_code=500, detail="An internal planning error occurred")
            return {
                "user_message": {"id": str(user_msg.id), "content": user_msg.content},
                "coordinator_message": {"id": final_message_id, "content": final_content},
                "itinerary": final_content or None,
                "run_id": None,
            }
        except HTTPException:
            raise
        except Exception:
            logger.exception("send_message (sync) failed for trip %s", trip_id)
            db.rollback()
            raise HTTPException(status_code=500, detail="An internal error occurred")

    # Streaming path — return SSE
    async def sse_generator():
        try:
            async for event in agent.run_orchestration_stream(db, trip_id, payload.content.strip(), user):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception:
            logger.exception("SSE generator failed for trip %s", trip_id)
            yield f"data: {json.dumps({'event': 'error', 'content': 'An internal error occurred'})}\n\n"
        finally:
            yield "event: done\ndata: {}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")
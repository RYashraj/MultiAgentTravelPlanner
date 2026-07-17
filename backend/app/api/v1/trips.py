import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Generator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.db.models import User, Trip, Message, Itinerary
from app.agents.supervisor import SupervisorAgent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trips", tags=["trips"])

# --- Pydantic Schemas ---
class TripCreate(BaseModel):
    destination: str
    status: str = "draft"

class TripOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    destination: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class MessageCreate(BaseModel):
    content: str

class MessageOut(BaseModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    sender: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True

class ItineraryOut(BaseModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    day_number: int
    title: str
    description: str | None
    activities: list | None
    created_at: datetime

    class Config:
        from_attributes = True

# --- Endpoints ---

@router.post("", response_model=TripOut, status_code=status.HTTP_201_CREATED)
def create_trip(
    trip_in: TripCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Creates a new travel itinerary (trip) for the authenticated user.
    """
    trip = Trip(
        user_id=current_user.id,
        destination=trip_in.destination,
        status=trip_in.status
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    logger.info(f"Created trip {trip.id} to {trip.destination} for user {current_user.email}")
    return trip


@router.get("", response_model=list[TripOut])
def list_trips(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves all trips belonging to the authenticated user.
    """
    trips = db.query(Trip).filter(Trip.user_id == current_user.id).order_by(Trip.created_at.desc()).all()
    return trips


@router.get("/{trip_id}/messages", response_model=list[MessageOut])
def get_trip_messages(
    trip_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves the message history for a specific trip.
    Guards access so users can only view their own trips' chats.
    """
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )
    if trip.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this trip's resources"
        )
    
    messages = db.query(Message).filter(Message.trip_id == trip_id).order_by(Message.created_at.ascii if hasattr(Message.created_at, "ascii") else Message.created_at).all()
    return messages


@router.get("/{trip_id}/itineraries", response_model=list[ItineraryOut])
def get_trip_itineraries(
    trip_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves the generated day-by-day itineraries for a specific trip.
    Guards access so users can only view their own trips' itineraries.
    """
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )
    if trip.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this trip's resources"
        )
    
    itineraries = db.query(Itinerary).filter(Itinerary.trip_id == trip_id).order_by(Itinerary.day_number).all()
    return itineraries


@router.post("/{trip_id}/messages")
async def send_trip_message(
    trip_id: uuid.UUID,
    message_in: MessageCreate,
    stream: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Sends a message to the trip chat workspace.
    Saves the user message, generates a dynamic mock AI response, and either:
    1. Returns a standard JSON list of the user & assistant messages (default).
    2. Streams the assistant message word-by-word via Server-Sent Events (SSE).
    """
    # 1. Validate trip ownership
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )
    if trip.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this trip's resources"
        )

    # 2. Save user message to database
    user_msg = Message(
        trip_id=trip_id,
        sender="user",
        content=message_in.content
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    # 3. Invoke SupervisorAgent to orchestrate and stream planning
    agent = SupervisorAgent()

    if stream:
        # SSE Generator
        async def event_generator():
            # Yield user message details first to confirm receipt
            yield f"event: user_message\ndata: {json.dumps({'id': str(user_msg.id), 'content': user_msg.content, 'sender': 'user'})}\n\n"
            await asyncio.sleep(0.1)

            async for step in agent.run_orchestration_stream(db, trip_id, message_in.content, current_user):
                event_type = step["event"]
                if event_type == "agent_log":
                    data = {"agent": step["agent"], "content": step["content"]}
                elif event_type == "message_chunk":
                    data = {"content": step["content"], "sender": step["sender"]}
                elif event_type == "message_complete":
                    data = {"id": step["id"], "content": step["content"], "sender": step["sender"]}
                else:
                    data = step

                yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    else:
        final_assistant_msg_content = ""
        final_assistant_msg_id = None
        async for step in agent.run_orchestration_stream(db, trip_id, message_in.content, current_user):
            if step["event"] == "message_complete":
                final_assistant_msg_content = step["content"]
                final_assistant_msg_id = uuid.UUID(step["id"])

        return {
            "user_message": {
                "id": user_msg.id,
                "trip_id": user_msg.trip_id,
                "sender": user_msg.sender,
                "content": user_msg.content,
                "created_at": user_msg.created_at
            },
            "assistant_message": {
                "id": final_assistant_msg_id or uuid.uuid4(),
                "trip_id": trip_id,
                "sender": "assistant",
                "content": final_assistant_msg_content,
                "created_at": datetime.now(timezone.utc)
            }
        }

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Generator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.db.models import User, Trip, Message

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

    # 3. Generate a helpful travel advisor response
    destination = trip.destination
    ai_reply_text = (
        f"Hi {current_user.full_name or 'there'}! 🌍 I am analyzing your request: '{message_in.content}' for your trip to {destination}.\n\n"
        f"As your VoyagerAI Planner, I recommend starting with these highlights in {destination}:\n"
        f"1. **Local Sightseeing**: Explore the historical landmarks and primary cultural districts.\n"
        f"2. **Culinary Spots**: Experience top-rated local dining and street foods.\n"
        f"3. **Stay**: Rest in a highly recommended boutique hotel central to transit.\n\n"
        f"I am spinning up my Logistics and Experience Agents to draft a comprehensive budget-friendly itinerary. "
        f"Let me know if you would like me to focus on specific flight times, hotel star ratings, or food options!"
    )

    if stream:
        # SSE Generator
        async def event_generator():
            full_reply = ""
            # Yield user message details first to confirm receipt
            yield f"event: user_message\ndata: {json.dumps({'id': str(user_msg.id), 'content': user_msg.content, 'sender': 'user'})}\n\n"
            await asyncio.sleep(0.1)

            # Yield assistant response word by word
            words = ai_reply_text.split(" ")
            for i, word in enumerate(words):
                chunk = (word + " ") if i < len(words) - 1 else word
                full_reply += chunk
                yield f"event: message_chunk\ndata: {json.dumps({'content': chunk, 'sender': 'assistant'})}\n\n"
                await asyncio.sleep(0.04)  # typing simulation speed
            
            # Write final assistant response to Database
            assistant_msg = Message(
                trip_id=trip_id,
                sender="assistant",
                content=ai_reply_text
            )
            db.add(assistant_msg)
            db.commit()
            db.refresh(assistant_msg)
            
            # Send completion signal
            yield f"event: message_complete\ndata: {json.dumps({'id': str(assistant_msg.id), 'content': ai_reply_text, 'sender': 'assistant'})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    else:
        # Save assistant message directly to Database
        assistant_msg = Message(
            trip_id=trip_id,
            sender="assistant",
            content=ai_reply_text
        )
        db.add(assistant_msg)
        db.commit()
        db.refresh(assistant_msg)

        return {
            "user_message": {
                "id": user_msg.id,
                "trip_id": user_msg.trip_id,
                "sender": user_msg.sender,
                "content": user_msg.content,
                "created_at": user_msg.created_at
            },
            "assistant_message": {
                "id": assistant_msg.id,
                "trip_id": assistant_msg.trip_id,
                "sender": assistant_msg.sender,
                "content": assistant_msg.content,
                "created_at": assistant_msg.created_at
            }
        }

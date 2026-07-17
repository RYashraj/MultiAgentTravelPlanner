import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.db.models import Itinerary
from app.repositories import TripRepository, MessageRepository, ItineraryRepository, UserRepository
from app.schemas.trips import TripCreate, TripResponse, MessageCreate, MessageResponse, ItineraryResponse, ChatResponse
from app.agents.supervisor import SupervisorAgent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trips", tags=["trips"])


def owned_trip(trip_id: uuid.UUID, user: CurrentUser, db: Session):
    trip = TripRepository(db).get_for_user(trip_id, user.id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return trip


@router.post("", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
def create_trip(
    payload: TripCreate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    UserRepository(db).upsert(user.id, user.email, user.full_name)
    return TripRepository(db).create(user.id, payload.destination.strip())


@router.get("", response_model=list[TripResponse])
def list_trips(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return TripRepository(db).list_for_user(user.id)


@router.get("/{trip_id}", response_model=TripResponse)
def get_trip(
    trip_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return owned_trip(trip_id, user, db)


@router.get("/{trip_id}/messages", response_model=list[MessageResponse])
def list_messages(
    trip_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    owned_trip(trip_id, user, db)
    return MessageRepository(db).list_for_trip(trip_id)


@router.get("/{trip_id}/itineraries", response_model=list[ItineraryResponse])
def get_trip_itineraries(
    trip_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    owned_trip(trip_id, user, db)
    itinerary = db.scalar(select(Itinerary).where(Itinerary.trip_id == trip_id))
    if not itinerary:
        return []
    
    # Adapter/Facade pattern: wrap the single content field in the format expected by the frontend
    return [
        ItineraryResponse(
            id=itinerary.id,
            trip_id=itinerary.trip_id,
            day_number=1,
            title="Consolidated Travel Plan",
            description=itinerary.content,
            activities={
                "flights": "Transit options verified",
                "accommodation": "Stays curated",
                "experiences": "Daily schedule structured"
            },
            created_at=itinerary.created_at
        )
    ]


@router.post("/{trip_id}/messages")
async def send_trip_message(
    trip_id: uuid.UUID,
    payload: MessageCreate,
    stream: bool = Query(default=False),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    trip = owned_trip(trip_id, user, db)
    
    # Save the user message to database using repository
    user_msg = MessageRepository(db).create(
        trip_id=trip_id,
        user_id=user.id,
        role="user",
        content=payload.content.strip()
    )

    agent = SupervisorAgent()

    if stream:
        async def event_generator():
            # Yield user message details first to confirm receipt
            yield f"event: user_message\ndata: {json.dumps({'id': str(user_msg.id), 'content': user_msg.content, 'role': 'user'})}\n\n"
            await asyncio.sleep(0.1)

            async for step in agent.run_orchestration_stream(db, trip_id, payload.content, user):
                event_type = step["event"]
                if event_type == "agent_log":
                    data = {"agent": step["agent"], "content": step["content"]}
                elif event_type == "message_chunk":
                    data = {"content": step["content"], "role": step["sender"]}
                elif event_type == "message_complete":
                    data = {"id": step["id"], "content": step["content"], "role": step["sender"]}
                else:
                    data = step

                yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    else:
        # Synced non-streaming call
        final_assistant_msg_content = ""
        final_assistant_msg_id = None
        async for step in agent.run_orchestration_stream(db, trip_id, payload.content, user):
            if step["event"] == "message_complete":
                final_assistant_msg_content = step["content"]
                final_assistant_msg_id = uuid.UUID(step["id"])

        user_msg_response = MessageResponse.model_validate(user_msg)
        
        # Retrieve the latest coordinator message & itinerary
        coord_msg = db.scalar(
            select(Itinerary).where(Itinerary.trip_id == trip_id)
        )
        itinerary_content = coord_msg.content if coord_msg else ""
        
        msg_db = MessageRepository(db).list_for_trip(trip_id)
        assistant_msg_obj = next((m for m in reversed(msg_db) if m.role == "assistant"), None)
        
        if assistant_msg_obj:
            coord_msg_response = MessageResponse.model_validate(assistant_msg_obj)
        else:
            coord_msg_response = MessageResponse(
                id=final_assistant_msg_id or uuid.uuid4(),
                role="assistant",
                content=final_assistant_msg_content,
                created_at=datetime.now(timezone.utc)
            )

        return ChatResponse(
            user_message=user_msg_response,
            coordinator_message=coord_msg_response,
            itinerary=itinerary_content,
            run_id=final_assistant_msg_id or uuid.uuid4()
        )

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TripCreate(BaseModel):
    destination: str = Field(min_length=2, max_length=255)


class TripResponse(BaseModel):
    id: uuid.UUID
    destination: str
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    dates: str | None = Field(default=None, max_length=100)
    budget: str | None = Field(default=None, max_length=100)
    preferences: list[str] = Field(default_factory=list)


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    user_message: dict
    coordinator_message: dict
    itinerary: str | None = None
    run_id: str | None = None


class ItineraryResponse(BaseModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    content: str
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}

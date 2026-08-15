import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class TripCreate(BaseModel):
    destination: str = Field(..., min_length=2, max_length=255, description="Target travel destination")
    origin: str | None = Field(default=None, max_length=255, description="Origin city or departure location")

    @field_validator("destination")
    @classmethod
    def validate_destination(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("Destination must contain at least 2 non-whitespace characters")
        if len(cleaned) > 255:
            raise ValueError("Destination must not exceed 255 characters")
        return cleaned


class TripResponse(BaseModel):
    id: uuid.UUID
    destination: str
    origin: str | None = None
    status: str
    is_saved: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000, description="User prompt content")
    dates: str | None = Field(default=None, max_length=100)
    budget: str | None = Field(default=None, max_length=100)
    preferences: list[str] = Field(default_factory=list)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Message content cannot be empty or whitespace only")
        if len(cleaned) > 4000:
            raise ValueError("Message content must not exceed 4000 characters")
        return cleaned

    @field_validator("dates")
    @classmethod
    def validate_dates(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        if len(cleaned) > 100:
            raise ValueError("Dates specification must not exceed 100 characters")
        return cleaned or None

    @field_validator("budget")
    @classmethod
    def validate_budget(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        if len(cleaned) > 100:
            raise ValueError("Budget specification must not exceed 100 characters")
        return cleaned or None


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

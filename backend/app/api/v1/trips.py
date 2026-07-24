import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agents.planner import planner_graph
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.rag.chroma_store import ChromaMemoryStore
from app.repositories import AgentRunRepository, ItineraryRepository, MessageRepository, TripRepository, UserRepository
from app.schemas.trips import ChatResponse, MessageCreate, MessageResponse, TripCreate, TripResponse

router = APIRouter(prefix="/trips", tags=["trips"])


def owned_trip(trip_id: uuid.UUID, user: CurrentUser, db: Session):
    trip = TripRepository(db).get_for_user(trip_id, user.id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return trip


@router.post("", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
def create_trip(payload: TripCreate, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    UserRepository(db).upsert(user.id, user.email, user.full_name)
    return TripRepository(db).create(user.id, payload.destination.strip())


@router.get("", response_model=list[TripResponse])
def list_trips(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return TripRepository(db).list_for_user(user.id)


@router.get("/{trip_id}", response_model=TripResponse)
def get_trip(trip_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return owned_trip(trip_id, user, db)


@router.get("/{trip_id}/messages", response_model=list[MessageResponse])
def list_messages(trip_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    owned_trip(trip_id, user, db)
    return MessageRepository(db).list_for_trip(trip_id)


from fastapi.responses import StreamingResponse
import json

@router.post("/{trip_id}/messages")
def send_message(trip_id: uuid.UUID, payload: MessageCreate, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    trip = owned_trip(trip_id, user, db)
    messages = MessageRepository(db)
    store = ChromaMemoryStore()

    state = {
        "trip_id": str(trip.id),
        "destination": trip.destination,
        "dates": payload.dates,
        "budget": payload.budget,
        "preferences": payload.preferences,
        "user_message": payload.content,
        "memory_context": [],
        "agent_outputs": {},
    }

    user_message = messages.create(trip.id, user.id, "user", payload.content.strip())
    store.embed_message(str(trip.id), str(user_message.id), "user", user_message.content)

    runs = AgentRunRepository(db)
    run = runs.start(trip.id, state)

    def event_generator():
        # Stream the graph execution steps
        for step in planner_graph.stream(state):
            step_name = list(step.keys())[0] if step else "unknown"
            yield f"data: {json.dumps({'type': 'status', 'step': step_name})}\n\n"
            
            if "merge" in step:
                # Final output
                coordinator_output = step["merge"]["agent_outputs"]["planner"]
                runs.complete(run, coordinator_output)
                coordinator_message = messages.create(trip.id, user.id, "assistant", coordinator_output["narrative"])
                store.embed_message(str(trip.id), str(coordinator_message.id), "assistant", coordinator_message.content)
                ItineraryRepository(db).save(trip.id, coordinator_output["narrative"])
                
                trip.status = "planning"
                db.commit()
                
                final_response = {
                    "type": "result",
                    "user_message": {"id": str(user_message.id), "content": user_message.content},
                    "coordinator_message": {"id": str(coordinator_message.id), "content": coordinator_message.content},
                    "itinerary": coordinator_output["narrative"],
                    "run_id": str(run.id),
                }
                yield f"data: {json.dumps(final_response)}\n\n"
        
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
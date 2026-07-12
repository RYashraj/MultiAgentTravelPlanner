"""
VoyagerAI backend entrypoint.

Run locally with:
    uvicorn app.main:app --reload
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager
from app.api.v1 import health
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.db.models import User, Trip

logging.basicConfig(level=logging.INFO)
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Automatically create tables for local development/testing
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(
    title="VoyagerAI API",
    description="Autonomous multi-agent AI travel planner — backend service",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_v1_prefix)


@app.get("/")
def root() -> dict:
    return {"message": "VoyagerAI API is running", "docs": "/docs"}

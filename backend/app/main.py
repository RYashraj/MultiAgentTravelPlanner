"""
VoyagerAI backend entrypoint.

Run locally with:
    uvicorn app.main:app --reload
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import health
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
settings = get_settings()

app = FastAPI(
    title="VoyagerAI API",
    description="Autonomous multi-agent AI travel planner — backend service",
    version="0.1.0",
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

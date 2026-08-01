"""
VoyagerAI backend entrypoint.

Run locally with:
    uvicorn app.main:app --reload
"""
import asyncio
import logging
import os
import urllib.request
import warnings
from contextlib import asynccontextmanager

warnings.filterwarnings("ignore", module="langgraph")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.staticfiles import StaticFiles

from app.api.v1 import auth, dashboard, health, trips
from app.core.auth_middleware import SupabaseJWTMiddleware
from app.core.config import get_settings
from app.db import models  # noqa: F401 — registers all ORM models on Base.metadata
from app.db.base import Base
from app.db.session import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(_STATIC_DIR, exist_ok=True)

_CDN_ASSETS = {
    "swagger-ui-bundle.js": "https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.9.0/swagger-ui-bundle.js",
    "swagger-ui.css": "https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.9.0/swagger-ui.css",
    "redoc.standalone.js": "https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js",
}


async def _prefetch_static_assets() -> None:
    """Download Swagger/ReDoc bundles once so /docs works without internet access."""
    for filename, url in _CDN_ASSETS.items():
        filepath = os.path.join(_STATIC_DIR, filename)
        if not os.path.exists(filepath):
            try:
                logger.info("Downloading static asset %s …", filename)
                await asyncio.to_thread(urllib.request.urlretrieve, url, filepath)
            except Exception as exc:
                logger.warning("Could not download %s: %s — will use CDN fallback", filename, exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Automatically create tables for local development / SQLite.
    # Production Postgres deployments should use `alembic upgrade head`.
    Base.metadata.create_all(bind=engine)
    await _prefetch_static_assets()
    yield


app = FastAPI(
    title="VoyagerAI API",
    description="Autonomous multi-agent AI travel planner — backend service",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(SupabaseJWTMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    js = (
        "/static/swagger-ui-bundle.js"
        if os.path.exists(os.path.join(_STATIC_DIR, "swagger-ui-bundle.js"))
        else "https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.9.0/swagger-ui-bundle.js"
    )
    css = (
        "/static/swagger-ui.css"
        if os.path.exists(os.path.join(_STATIC_DIR, "swagger-ui.css"))
        else "https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.9.0/swagger-ui.css"
    )
    return get_swagger_ui_html(
        openapi_url=app.openapi_url or "/openapi.json",
        title=f"{app.title} — Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url=js,
        swagger_css_url=css,
    )


@app.get("/redoc", include_in_schema=False)
async def custom_redoc():
    js = (
        "/static/redoc.standalone.js"
        if os.path.exists(os.path.join(_STATIC_DIR, "redoc.standalone.js"))
        else "https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"
    )
    return get_redoc_html(
        openapi_url=app.openapi_url or "/openapi.json",
        title=f"{app.title} — ReDoc",
        redoc_js_url=js,
    )


app.include_router(health.router, prefix=settings.api_v1_prefix)
app.include_router(trips.router, prefix=settings.api_v1_prefix)
app.include_router(dashboard.router, prefix=settings.api_v1_prefix)
app.include_router(auth.router, prefix=settings.api_v1_prefix)


@app.get("/")
def root() -> dict:
    return {"message": "VoyagerAI API is running", "docs": "/docs"}

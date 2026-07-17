"""
VoyagerAI backend entrypoint.

Run locally with:
    uvicorn app.main:app --reload
"""
import logging
import os
import urllib.request


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html

from contextlib import asynccontextmanager
from app.api.v1 import health, trips
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.db.models import User, Trip, Message, Itinerary, AgentRun

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()

static_dir_path = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir_path, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Automatically create tables for local development/testing
    Base.metadata.create_all(bind=engine)
    
    # Pre-download Swagger/ReDoc assets locally for offline use or when jsdelivr is blocked
    os.makedirs(static_dir_path, exist_ok=True)
    assets = {
        "swagger-ui-bundle.js": "https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.9.0/swagger-ui-bundle.js",
        "swagger-ui.css": "https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.9.0/swagger-ui.css",
        "redoc.standalone.js": "https://cdnjs.cloudflare.com/ajax/libs/redoc/2.1.3/redoc.standalone.js",
    }
    for filename, url in assets.items():
        filepath = os.path.join(static_dir_path, filename)
        if not os.path.exists(filepath):
            try:
                logger.info(f"Downloading static asset {filename} for local offline docs...")
                urllib.request.urlretrieve(url, filepath)
            except Exception as e:
                logger.warning(f"Could not download {filename} from CDN, will fallback to remote URL: {e}")
                
    yield

app = FastAPI(
    title="VoyagerAI API",
    description="Autonomous multi-agent AI travel planner — backend service",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the static directory
app.mount("/static", StaticFiles(directory=static_dir_path), name="static")

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    swagger_js = "/static/swagger-ui-bundle.js" if os.path.exists(os.path.join(static_dir_path, "swagger-ui-bundle.js")) else "https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.9.0/swagger-ui-bundle.js"
    swagger_css = "/static/swagger-ui.css" if os.path.exists(os.path.join(static_dir_path, "swagger-ui.css")) else "https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.9.0/swagger-ui.css"
    
    return get_swagger_ui_html(
        openapi_url=app.openapi_url or "/openapi.json",
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url=swagger_js,
        swagger_css_url=swagger_css,
    )

@app.get("/redoc", include_in_schema=False)
async def custom_redoc_html():
    redoc_js = "/static/redoc.standalone.js" if os.path.exists(os.path.join(static_dir_path, "redoc.standalone.js")) else "https://cdnjs.cloudflare.com/ajax/libs/redoc/2.1.3/redoc.standalone.js"
    
    return get_redoc_html(
        openapi_url=app.openapi_url or "/openapi.json",
        title=app.title + " - ReDoc",
        redoc_js_url=redoc_js,
    )

app.include_router(health.router, prefix=settings.api_v1_prefix)
app.include_router(trips.router, prefix=settings.api_v1_prefix)


@app.get("/")
def root() -> dict:
    return {"message": "VoyagerAI API is running", "docs": "/docs"}


"""FastAPI application entry point.

Creates the app, configures CORS for the dashboard, and mounts the API
router. Run locally with ``fastapi dev app/main.py`` or, in Docker,
``fastapi run app/main.py``.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.wp_routes import router as wp_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="WordPress Automation Agent",
    version="0.1.0",
    description="Agentic WordPress site builder — REST/WP-CLI tool layer.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(wp_router)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {"service": "wordpress-automation-agent", "status": "running"}

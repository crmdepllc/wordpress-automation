"""API routes.

The REST surface between the Next.js dashboard and the LangGraph agent. In
Sprint 1 this is just a health check and the ``/api/ping`` spike that drives
the agent end-to-end.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent.graph import ping_graph

router = APIRouter()


class PingRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Prompt to send to Claude.")


class PingResponse(BaseModel):
    response: str


@router.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Liveness probe used by Docker Compose and the frontend."""
    return {"status": "ok"}


@router.post("/api/ping", response_model=PingResponse, tags=["agent"])
async def ping(request: PingRequest) -> PingResponse:
    """Run the single-node ping graph and return Claude's reply.

    This is the Sprint 1 end-to-end path: frontend → FastAPI → LangGraph →
    Claude → back. No WordPress writes happen here, so no approval gate is
    needed yet.
    """
    try:
        result = await ping_graph.ainvoke({"prompt": request.prompt})
    except RuntimeError as exc:  # missing API key, etc. — clear 400
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # upstream/model failure
        raise HTTPException(status_code=502, detail=f"Agent error: {exc}") from exc
    return PingResponse(response=result["response"])

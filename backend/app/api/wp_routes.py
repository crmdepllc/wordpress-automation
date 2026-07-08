"""HTTP routes for WordPress site management and the gated agent path.

  POST /api/wp/sites      — register/update a site's credentials (encrypted)
  GET  /api/wp/sites      — list registered site slugs
  POST /api/wp/plan       — natural language -> one proposed tool call (no write)
  POST /api/wp/execute    — run a tool; writes apply only when approved=True
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.wp_agent import WpAgent, run_approved
from app.crypto import EncryptionKeyMissingError
from app.db.session import get_session
from app.wp.credentials import list_site_slugs, upsert_site

router = APIRouter(prefix="/api/wp", tags=["wordpress"])


class SiteIn(BaseModel):
    slug: str
    name: str
    base_url: str
    wp_username: str
    wp_app_password: str
    wpcli_transport: str = "ssh"
    ssh_host: str | None = None
    ssh_port: int = 22
    ssh_user: str | None = None
    ssh_private_key: str | None = None
    wp_cli_path: str = "wp"
    cli_cwd: str | None = None
    cli_env: dict[str, str] | None = None


@router.post("/sites")
async def register_site(
    body: SiteIn, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    try:
        site = await upsert_site(session, **body.model_dump())
    except EncryptionKeyMissingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "slug": site.slug}


@router.get("/sites")
async def get_sites(session: AsyncSession = Depends(get_session)) -> dict[str, list[str]]:
    return {"sites": await list_site_slugs(session)}


class PlanIn(BaseModel):
    instruction: str = Field(..., min_length=1)
    site_slug: str


@router.post("/plan")
async def plan(body: PlanIn) -> dict[str, Any]:
    """Propose one tool call from natural language. Never writes."""
    try:
        proposal = await WpAgent().propose(body.instruction, body.site_slug)
    except Exception as exc:  # missing key, model error
        raise HTTPException(status_code=400, detail=f"Planning failed: {exc}") from exc
    if proposal is None:
        return {"status": "no_action", "message": "No tool was selected."}
    return {"status": "proposed", "proposal": proposal.model_dump()}


class ExecuteIn(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    approved: bool = False


@router.post("/execute")
async def execute(body: ExecuteIn) -> dict[str, Any]:
    """Run a tool. Write tools apply only when ``approved`` is true; otherwise
    they return a ``needs_approval`` preview."""
    from app.agent.wp_agent import TOOLS_BY_NAME

    if body.tool not in TOOLS_BY_NAME:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {body.tool}")
    try:
        if body.approved:
            result = await run_approved(body.tool, body.args)
        else:
            result = await TOOLS_BY_NAME[body.tool].ainvoke(body.args)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Tool error: {exc}") from exc
    return {"result": result}

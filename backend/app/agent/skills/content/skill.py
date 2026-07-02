"""Content pipeline: brief → PostDraft. Writing happens in the tool."""

from __future__ import annotations

from app.agent.skills.content.generator import ContentGenerator, build_content_generator
from app.agent.skills.content.schema import PostDraft


async def generate_post_draft(
    brief: str, *, generator: ContentGenerator | None = None
) -> PostDraft:
    return await (generator or build_content_generator()).generate(brief)

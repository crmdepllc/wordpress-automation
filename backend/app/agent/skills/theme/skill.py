"""Theme pipeline: brief → ThemeSpec (application lives in applier.py)."""

from __future__ import annotations

from app.agent.skills.theme.generator import ThemeGenerator, build_theme_generator
from app.agent.skills.theme.schema import ThemeSpec


async def generate_theme(
    brief: str, *, generator: ThemeGenerator | None = None
) -> ThemeSpec:
    return await (generator or build_theme_generator()).generate(brief)

"""Theme settings IR.

Hex colors are legitimate here — this is generated *site* content applied to the
managed WordPress site, not our own dashboard UI (which uses design tokens).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ThemePalette(BaseModel):
    primary: str = "#1a1a1a"
    secondary: str = "#4a4a4a"
    accent: str = "#0066ff"
    text: str = "#222222"
    background: str = "#ffffff"


class ThemeFonts(BaseModel):
    heading: str = "Inter"
    body: str = "Inter"


class ThemeSpec(BaseModel):
    """A generated theme: palette, fonts, and a footer line."""

    palette: ThemePalette = Field(default_factory=ThemePalette)
    fonts: ThemeFonts = Field(default_factory=ThemeFonts)
    footer_text: str = ""

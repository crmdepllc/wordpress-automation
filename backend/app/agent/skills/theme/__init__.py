"""Theme customizer skill — brief → palette/fonts applied via WP-CLI + Elementor kit."""

from app.agent.skills.theme.applier import apply_theme
from app.agent.skills.theme.schema import ThemeSpec
from app.agent.skills.theme.skill import generate_theme

__all__ = ["ThemeSpec", "generate_theme", "apply_theme"]

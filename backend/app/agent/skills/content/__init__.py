"""Content generation skill — brief → a post draft (title, body, terms)."""

from app.agent.skills.content.schema import PostDraft
from app.agent.skills.content.skill import generate_post_draft

__all__ = ["PostDraft", "generate_post_draft"]

"""The content draft IR the model fills."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PostDraft(BaseModel):
    """A blog post the agent proposes. Category/tag are human names; the tool
    resolves them to term ids via find-or-create."""

    title: str
    content: str  # HTML/blocks body
    excerpt: str = ""
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

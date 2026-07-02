"""SEO metadata IR."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SchemaType = Literal["Article", "WebPage", "Organization", "LocalBusiness", "Product"]


class SeoMeta(BaseModel):
    """Generated SEO metadata for one page/post."""

    title: str = Field(..., description="Meta title, ideally ≤ 60 chars")
    description: str = Field(..., description="Meta description, ideally ≤ 160 chars")
    schema_type: SchemaType = "Article"

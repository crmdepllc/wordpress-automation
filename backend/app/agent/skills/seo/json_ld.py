"""Build a JSON-LD schema.org object from generated SEO metadata."""

from __future__ import annotations

from typing import Any

from app.agent.skills.seo.schema import SeoMeta


def build_json_ld(seo: SeoMeta, *, name: str, url: str) -> dict[str, Any]:
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": seo.schema_type,
        "name": name,
        "url": url,
        "description": seo.description,
    }
    if seo.schema_type == "Article":
        data["headline"] = seo.title
    return data

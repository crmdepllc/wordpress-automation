"""SEO pipeline: subject → SeoMeta, and SeoMeta → provider meta-key dict."""

from __future__ import annotations

import json
from typing import Any

from app.agent.skills.seo.generator import SeoGenerator, build_seo_generator
from app.agent.skills.seo.json_ld import build_json_ld
from app.agent.skills.seo.providers import meta_keys
from app.agent.skills.seo.schema import SeoMeta


async def generate_seo(
    subject: str, *, generator: SeoGenerator | None = None
) -> SeoMeta:
    return await (generator or build_seo_generator()).generate(subject)


def seo_to_meta(
    seo: SeoMeta, *, provider: str, name: str, url: str
) -> dict[str, Any]:
    """Map SeoMeta to the post-meta dict written via REST."""
    keys = meta_keys(provider)
    return {
        keys["title"]: seo.title,
        keys["description"]: seo.description,
        # JSON-LD emitted by the companion plugin; stored as its own meta.
        "_seo_schema_jsonld": json.dumps(build_json_ld(seo, name=name, url=url)),
    }

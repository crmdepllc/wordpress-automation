"""SEO skill — generate meta title/description + JSON-LD, as provider meta keys."""

from app.agent.skills.seo.schema import SeoMeta
from app.agent.skills.seo.skill import generate_seo, seo_to_meta

__all__ = ["SeoMeta", "generate_seo", "seo_to_meta"]

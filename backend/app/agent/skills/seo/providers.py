"""SEO provider → post-meta key mapping.

Yoast and RankMath store the SEO title/description as post meta under different
keys. The skill writes whichever the site uses (selectable per call); adding a
provider is a new entry here.
"""

from __future__ import annotations

PROVIDERS: dict[str, dict[str, str]] = {
    "yoast": {
        "title": "_yoast_wpseo_title",
        "description": "_yoast_wpseo_metadesc",
    },
    "rankmath": {
        "title": "rank_math_title",
        "description": "rank_math_description",
    },
}

DEFAULT_PROVIDER = "yoast"


def meta_keys(provider: str) -> dict[str, str]:
    return PROVIDERS.get(provider, PROVIDERS[DEFAULT_PROVIDER])

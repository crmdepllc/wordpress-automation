"""A small catalog mapping common needs to plugin slugs.

Lets the agent go from an intent ("a contact form", "caching") to a concrete,
vetted slug it can install. Not exhaustive — the plugin *search* tool covers the
long tail.
"""

from __future__ import annotations

# intent keyword -> (slug, human name)
_CATALOG: dict[str, tuple[str, str]] = {
    "contact form": ("contact-form-7", "Contact Form 7"),
    "form": ("contact-form-7", "Contact Form 7"),
    "caching": ("w3-total-cache", "W3 Total Cache"),
    "cache": ("w3-total-cache", "W3 Total Cache"),
    "seo": ("wordpress-seo", "Yoast SEO"),
    "security": ("wordfence", "Wordfence Security"),
    "backup": ("updraftplus", "UpdraftPlus"),
    "ecommerce": ("woocommerce", "WooCommerce"),
    "shop": ("woocommerce", "WooCommerce"),
    "analytics": ("google-site-kit", "Site Kit by Google"),
}


def recommend_plugin(need: str) -> dict[str, str] | None:
    """Return {slug, name} for a stated need, or None if unknown."""
    lowered = need.lower()
    for keyword, (slug, name) in _CATALOG.items():
        if keyword in lowered:
            return {"slug": slug, "name": name}
    return None

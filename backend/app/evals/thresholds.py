"""Per-skill minimum eval scores. A skill scoring below its threshold fails CI.

Fixed floors, not a ratcheting baseline file — simple to reason about, and a
PR doesn't need to touch this file just because it nudged a score up.
"""

from __future__ import annotations

THRESHOLDS: dict[str, float] = {
    "elementor": 90.0,
    "content": 90.0,
    "images": 90.0,
    "stack": 90.0,
    "seo": 90.0,
    "theme": 85.0,
    "plugins": 85.0,
    "orchestrator": 90.0,
}


def threshold_for(skill: str) -> float:
    return THRESHOLDS.get(skill, 90.0)

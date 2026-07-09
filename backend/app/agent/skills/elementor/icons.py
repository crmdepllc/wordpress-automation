"""A verified-safe Font Awesome icon allowlist.

Elementor's SVG icon renderer (``elementor/core/page-assets/data-managers/
font-icon-svg/font-awesome.php``) looks icons up by name in a *bundled*
Font Awesome dataset — ``elementor/assets/lib/font-awesome/json/solid.json``
— not whatever Font Awesome version is documented publicly. That bundled
dataset is pinned to an older Font Awesome release (5.15.3 as of Elementor
4.1.4). An icon name that's valid in modern Font Awesome but missing from
that bundled set (e.g. ``mountain-sun``, added in FA 6.2) produces PHP
warnings (``Undefined array key``, "Trying to access array offset on null")
and a broken/blank icon on the live page — confirmed against a real
Elementor install.

This list was built by cross-checking common icon names against a real
install's bundled ``solid.json`` — every entry here is confirmed present.
Anything the model picks that isn't in this list is defensively swapped for
``DEFAULT_ICON`` before the page is ever built (see ``skill.py``), so a
non-compliant model response can't reintroduce this bug.
"""

from __future__ import annotations

ALLOWED_ICONS: frozenset[str] = frozenset(
    {
        "ambulance", "anchor", "apple-alt", "atom", "award", "baby",
        "basketball-ball", "battery-full", "bed", "beer", "bell", "bicycle",
        "biking", "binoculars", "birthday-cake", "bolt", "book", "box",
        "boxes", "brain", "briefcase", "broom", "building", "calendar-alt",
        "calendar-check", "camera", "camera-retro", "campground", "car",
        "carrot", "certificate", "chart-line", "chart-pie", "check",
        "check-circle", "child", "clipboard-check", "clock", "cloud",
        "cloud-upload-alt", "cocktail", "code", "coffee", "cog", "coins",
        "comment-dots", "comments", "compass", "concierge-bell", "couch",
        "credit-card", "crown", "database", "dna", "door-open", "dumbbell",
        "envelope", "eye", "feather-alt", "filter", "fingerprint", "fire",
        "first-aid", "fish", "flag", "flask", "football-ball", "futbol",
        "gem", "gift", "glass-cheers", "glasses", "globe", "golf-ball",
        "graduation-cap", "hamburger", "handshake", "hands-helping",
        "hard-hat", "headset", "heart", "heartbeat", "hiking", "home",
        "hospital", "hourglass-half", "ice-cream", "image", "industry",
        "key", "laptop-code", "leaf", "life-ring", "lightbulb", "list",
        "lock", "luggage-cart", "magic", "map", "map-marker-alt", "map-pin",
        "medal", "microscope", "mobile-alt", "moon", "mountain", "music",
        "paint-brush", "palette", "passport", "paw", "pencil-alt", "pen-nib",
        "phone", "phone-alt", "pills", "pizza-slice", "plane",
        "plane-departure", "plug", "quote-left", "quote-right", "recycle",
        "ring", "rocket", "route", "ruler", "running", "search", "seedling",
        "server", "shield-alt", "ship", "shipping-fast", "shoe-prints",
        "shopping-bag", "shopping-cart", "smile", "snowflake", "solar-panel",
        "star", "stethoscope", "stopwatch", "store", "suitcase", "sun",
        "swimmer", "syringe", "tasks", "thumbs-up", "tint", "tools", "tooth",
        "tree", "trophy", "truck", "tshirt", "umbrella", "umbrella-beach",
        "unlock", "user", "users", "user-shield", "utensils", "video",
        "volleyball-ball", "walking", "warehouse", "water", "weight-hanging",
        "wifi", "wind", "wine-bottle", "wine-glass-alt", "wrench",
    }
)

DEFAULT_ICON = "star"


def safe_icon(value: str) -> str:
    """Return a verified-safe icon value in Elementor's expected ``"fas fa-<name>"``
    form, or the default in that same form.

    Tolerates the forms the model may emit as input: ``"fas fa-camera"``,
    ``"fa-camera"``, or a bare ``"camera"`` — but the *output* is always fully
    prefixed. Elementor's own icon parser (``Font_Awesome::get_config()``)
    regex-matches ``/fa(.*) fa-/`` against the stored value to extract the
    bare name; a value with no ``"fa-"`` substring (e.g. a bare name with the
    prefix stripped) fails that match just as badly as an unknown icon does —
    found via live verification when an earlier version of this function
    stripped the prefix instead of preserving it.
    """
    token = value.strip().split()[-1] if value.strip() else ""
    name = token.removeprefix("fa-")
    safe_name = name if name in ALLOWED_ICONS else DEFAULT_ICON
    return f"fas fa-{safe_name}"

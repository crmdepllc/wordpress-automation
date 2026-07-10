# Elementor section example library

Each file is one **section template** the builder fills and stitches into a
page. The format wraps a real Elementor section element with a small `meta`
header the builder uses:

```jsonc
{
  "meta": {
    "section_type": "hero",
    "layout": "single",            // "single" | "grid" | "stack"
    "scalar_slots": ["heading"],   // {{heading}} tokens filled from SectionSpec.content
    "item_slots": ["title"]        // {{item.title}} tokens, one clone per SectionSpec.items[]
  },
  "template": { /* an Elementor `elType:"section"` element with {{tokens}} */ }
}
```

- **`single`** sections have one fixed column; scalar slots are filled in place.
- **`grid`** and **`stack`** sections wrap their repeated content one level
  deeper: `section -> column -> [optional heading widgets..., inner section]`.
  The **inner section** (always the last element in the outer column) holds
  the item prototype. This nesting exists so a heading/eyebrow/subheading can
  sit above the repeated items — an Elementor section's columns lay out side
  by side, so a title can't share a row with the item columns; nesting a
  second section one level in is the real Elementor pattern for a
  title-above-grid layout (`validator.py` already permits a section as a
  column's child).
  - **`grid`**: the inner section has exactly one column — the **item
    prototype**. The builder clones it once per `items[]` entry and splits
    the column width evenly (side by side).
  - **`stack`**: the inner section has one column containing exactly one
    widget — the **item prototype**. The builder clones the widget once per
    `items[]` entry into that single column (stacked vertically, not side by
    side). Used for things like FAQ, where each item is one row, not one
    column (`faq.json`).

A slot named `background_color` is always optional (a hex code, or omit it to
use the site's default background) — see `hero.json`/`footer.json`/etc. Pair it
with `heading_color` (also optional) so text stays readable against a custom
background — the generator is instructed to set both together, and to
alternate `background_color` across consecutive sections for visual rhythm.
A slot named `accent_color` is optional — where offered, it drives both button
backgrounds *and* icon-circle backgrounds (icon-box widgets' `primary_color`),
so the generator is instructed to reuse one value for every `accent_color`
slot on a page rather than a different accent per section (enforced by the
`accent_color_consistent`/`accent_color_applied` eval checks).
Slots named `icon` expect an Elementor icon-picker value:
`{"value": "fas fa-bolt", "library": "fa-solid"}` — the token only fills the
`value` half; the `library` is fixed at `fa-solid` in the template.
`eyebrow` is a short overline label rendered above a section's main heading
(e.g. "WHY CHOOSE US"), styled in `accent_color` — distinct from `heading`.

A slot named `image_prompt` (currently only on `hero.json`/`about.json`) is
optional and, unlike every other content slot, is never shown on the page —
Claude may set it as a structural decision (does this section want an image,
roughly what should it depict), and `app/agent/skills/images/resolver.py`
turns it into a real image: generated via Gemini, uploaded to the WP media
library, replacing `image_prompt` with `image_url`/`image_id` before the
template's `{{image_url}}`/`{{image_id}}` tokens get filled. This only
happens inside the gated `wp_create_elementor_page` tool, post-approval — the
offline `generate_elementor_page` pipeline (used by tests/evals) never
resolves it, so an unfilled `image_prompt` always builds without an image:
`builder.py`'s `_finalize_image_widgets` drops any `image` widget left with
an empty url rather than shipping a broken image box.

The builder regenerates every element `id` on build, so the ids here are
placeholders.

> ⚠️ **Reference scaffolds, verified against a live sandbox, not a real
> editor export.** These are modeled on Elementor's documented
> `section → column → widget` structure — no live Elementor editor session was
> used to build them (per AGENTS.md rule #3's ideal). Every template here
> **has** been written via the real REST/WP-CLI path against a live
> WordPress + Elementor instance and visually confirmed to render (see the
> Sprint 8/companion-plugin follow-up notes in `progress-tracker.md`) — that
> live pass is what caught two real bugs a purely offline/structural check
> couldn't: the Toggle widget needs a `tabs` repeater (not flat
> `tab_title`/`tab_content`), and the Elementor Kit's `_elementor_page_settings`
> meta must be written as a real PHP array (`wp post meta update --format=json`),
> not a JSON string. Still worth replacing with genuine editor exports if/when
> a live Elementor editor session is available — the integration render eval
> (`tests/integration/test_elementor_render.py`) is the ongoing gate.

> ⚠️ **Card-styling pass (style-only production-quality upgrade, no new
> images): a few control names are best-known, not live-confirmed yet.**
> Added in this pass: column-level `_border_radius`/`_box_shadow_box_shadow_type`/
> `_box_shadow_box_shadow`/`_padding` (`features.json`, `testimonials.json`,
> `pricing.json`, `about.json`, `contact.json`), icon-box `view: "stacked"` /
> `shape: "circle"` / `primary_color` / `secondary_color` (`features.json`,
> `badges.json`), icon-list `icon_color` (`contact.json`), and section-level
> `border_border`/`border_width`/`border_color` (`footer.json`). These are
> standard Elementor "advanced tab" / widget-style control names, but per the
> same rule #3 caveat above, they have **not yet been visually confirmed
> against a live install** the way the rest of this library has — live-verify
> before fully trusting them, and fix forward the same way the Toggle/Kit bugs
> above were fixed if a name turns out wrong. Two new section types were also
> added: `about` (single-column bio block, no photo) and `badges` (a small
> icon-circle trust-badge row) — both style-only substitutes for the
> photo/logo-based versions a real design would use.

> ✅ **Image widget (Gemini image generation, `hero.json`/`about.json`):
> live-verified.** The `image` widget settings shape
> (`{"image": {"url", "id"}, "image_size", "align"}`) was built via
> `build_and_validate` → REST write → live fetch against a real WordPress +
> Elementor sandbox (both sections in the same page): both widgets rendered
> with the correct `wp-image-<id>` class and the right size variant
> (`size-large` on `hero`, `size-medium_large` on `about`), no PHP
> warnings/errors introduced, and the string attachment id round-tripped
> correctly through `builder.py`'s int coercion. See `progress-tracker.md`'s
> "Gemini image generation" entry.

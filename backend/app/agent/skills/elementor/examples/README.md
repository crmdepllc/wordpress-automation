# Elementor section example library

Each file is one **section template** the builder fills and stitches into a
page. The format wraps a real Elementor section element with a small `meta`
header the builder uses:

```jsonc
{
  "meta": {
    "section_type": "hero",
    "layout": "single",            // "single" | "grid"
    "scalar_slots": ["heading"],   // {{heading}} tokens filled from SectionSpec.content
    "item_slots": ["title"]        // {{item.title}} tokens, one clone per SectionSpec.items[]
  },
  "template": { /* an Elementor `elType:"section"` element with {{tokens}} */ }
}
```

- **`single`** sections have one fixed column; scalar slots are filled in place.
- **`grid`** sections have exactly one column in the template — the **item
  prototype**. The builder clones it once per `items[]` entry and splits the
  column width evenly (side by side).
- **`stack`** sections have one column containing exactly one widget — the
  **item prototype**. The builder clones the widget once per `items[]` entry
  into that single column (stacked vertically, not side by side). Used for
  things like FAQ, where each item is one row, not one column (`faq.json`).

A slot named `background_color` is always optional (a hex code, or omit it to
use the site's default background) — see `hero.json`/`footer.json`/etc. Pair it
with `heading_color` (also optional) so text stays readable against a custom
background — the generator is instructed to set both together.
Slots named `icon` expect an Elementor icon-picker value:
`{"value": "fas fa-bolt", "library": "fa-solid"}` — the token only fills the
`value` half; the `library` is fixed at `fa-solid` in the template.

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

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
  column width evenly.

The builder regenerates every element `id` on build, so the ids here are
placeholders.

> ⚠️ **Reference scaffolds, not verified exports.** These are modeled on
> Elementor's documented `section → column → widget` structure so the skill and
> its evals are exercisable without a live editor. Per AGENTS.md rule #3, before
> trusting these in production they should be **replaced/augmented with genuine
> `_elementor_data` exported from a real Elementor page** (build the page in the
> editor, export, drop the section JSON in here). The integration render eval
> (`tests/integration/test_elementor_render.py`) is the gate that confirms a
> template actually renders.

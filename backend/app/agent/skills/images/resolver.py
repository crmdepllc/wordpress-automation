"""Resolve a ``PageSpec``'s ``image_prompt`` design slots into real images.

Claude may set ``image_prompt`` on a section that supports it (see
``elementor/generator.py``'s ``DESIGN_SLOTS``) as a structural decision — this
module is what turns that prompt into an actual image: generate via Gemini,
upload to the WordPress media library, then swap the prompt for the uploaded
image's URL/id so the builder's ``{{image_url}}``/``{{image_id}}`` tokens have
something real to fill.

This only ever runs inside the already-gated ``wp_create_elementor_page``
tool, after approval — both the Gemini call and the WP media upload are real
work (an API call and a site write), so per AGENTS.md rule 1 neither may
happen during planning, before a human has approved the page.

A failed image (Gemini quota/API error, a bad upload, etc.) degrades that one
section to "no image" rather than failing the whole page — the same state as
a section whose ``image_prompt`` was never set, which ``builder.py``'s
``_finalize_image_widgets`` already drops cleanly. The rest of a page (real
copy, real structure) shouldn't be thrown away because one image call failed.
"""

from __future__ import annotations

import logging
import secrets

from app.agent.skills.elementor.schema import PageSpec
from app.agent.skills.images.generator import ImageGenerator, build_image_generator
from app.wp.rest_client import WordPressRestClient

logger = logging.getLogger("agent.skills.images")

IMAGE_PROMPT_SLOT = "image_prompt"


async def resolve_images(
    spec: PageSpec,
    wp: WordPressRestClient,
    *,
    image_generator: ImageGenerator | None = None,
) -> PageSpec:
    """Replace every filled ``image_prompt`` slot with an uploaded image's
    ``image_url``/``image_id``. Sections without a prompt are untouched. A
    section whose image fails to generate/upload is left without one (logged,
    not raised) instead of failing the whole page."""
    gen = image_generator or build_image_generator()
    sections = []
    for section in spec.sections:
        prompt = section.content.get(IMAGE_PROMPT_SLOT, "").strip()
        content = {k: v for k, v in section.content.items() if k != IMAGE_PROMPT_SLOT}
        if not prompt:
            sections.append(section)
            continue
        try:
            image_bytes = await gen.generate(prompt)
            filename = f"{section.type}-{secrets.token_hex(4)}.png"
            media = await wp.upload_media(filename, image_bytes, "image/png")
        except Exception:
            logger.warning(
                "image resolution failed for %s section (prompt=%r) — "
                "building without an image for this section",
                section.type, prompt, exc_info=True,
            )
            sections.append(section.model_copy(update={"content": content}))
            continue
        content["image_url"] = media.source_url
        content["image_id"] = str(media.id)
        sections.append(section.model_copy(update={"content": content}))
    return spec.model_copy(update={"sections": sections})

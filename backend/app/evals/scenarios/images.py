"""Images golden dataset: resolve_images against fakes (Gemini + WP mocked)."""

from __future__ import annotations

from app.agent.skills.elementor.schema import PageSpec, SectionSpec
from app.agent.skills.images.resolver import resolve_images
from app.evals.scoring import CheckResult, Scenario
from app.wp.schemas import MediaItem


class _FakeImageGenerator:
    def __init__(self):
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> bytes:
        self.prompts.append(prompt)
        return b"fake-bytes"


class _FakeWp:
    def __init__(self):
        self.uploads: list[tuple[str, bytes, str]] = []

    async def upload_media(self, filename: str, content: bytes, mime_type: str) -> MediaItem:
        self.uploads.append((filename, content, mime_type))
        media_id = len(self.uploads)
        return MediaItem(id=media_id, source_url=f"http://wp.test/{media_id}.png", mime_type=mime_type)


async def _run_resolves_requested_image() -> list[CheckResult]:
    spec = PageSpec(
        title="Studio",
        sections=[
            SectionSpec(type="hero", content={"heading": "Hi", "image_prompt": "a bright studio"}),
            SectionSpec(type="features", content={"heading": "What we do"}),
        ],
    )
    wp = _FakeWp()
    image_gen = _FakeImageGenerator()
    result = await resolve_images(spec, wp, image_generator=image_gen)
    hero, features = result.sections

    return [
        CheckResult("image_generated_once", image_gen.prompts == ["a bright studio"], weight=2),
        CheckResult("uploaded_once_to_wp", len(wp.uploads) == 1, weight=2),
        CheckResult("upload_is_png", wp.uploads[0][2] == "image/png" if wp.uploads else False, weight=1),
        CheckResult("prompt_removed_from_content", "image_prompt" not in hero.content, weight=1),
        CheckResult(
            "image_url_and_id_populated",
            bool(hero.content.get("image_url")) and bool(hero.content.get("image_id")),
            weight=2,
        ),
        CheckResult("other_content_untouched", hero.content.get("heading") == "Hi", weight=1),
        CheckResult(
            "section_without_prompt_untouched",
            features.content == {"heading": "What we do"} and not wp.uploads[1:],
            weight=1,
        ),
    ]


async def _run_noop_when_no_prompt() -> list[CheckResult]:
    spec = PageSpec(title="X", sections=[SectionSpec(type="hero", content={"heading": "Hi"})])
    wp = _FakeWp()
    result = await resolve_images(spec, wp, image_generator=_FakeImageGenerator())

    return [
        CheckResult("no_upload_attempted", wp.uploads == [], weight=2),
        CheckResult("content_unchanged", result.sections[0].content == {"heading": "Hi"}, weight=2),
    ]


SCENARIOS = [
    Scenario(name="hero image_prompt resolves and uploads", run=_run_resolves_requested_image),
    Scenario(name="no image_prompt is a no-op", run=_run_noop_when_no_prompt),
]

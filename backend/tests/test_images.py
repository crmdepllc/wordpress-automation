"""Unit tests for the images skill (Gemini client + WP media resolution mocked)."""

from __future__ import annotations

import pytest

from app.agent.skills.elementor.schema import PageSpec, SectionSpec
from app.agent.skills.images.generator import GeminiImageGenerator, ImageGenerationError
from app.agent.skills.images.resolver import resolve_images
from app.wp.schemas import MediaItem


# --- GeminiImageGenerator -------------------------------------------------


class _FakeInlineData:
    def __init__(self, data: bytes | None):
        self.data = data


class _FakePart:
    def __init__(self, data: bytes | None):
        self.inline_data = _FakeInlineData(data) if data is not None else None


class _FakeCandidate:
    def __init__(self, parts: list[_FakePart]):
        class _Content:
            pass

        self.content = _Content()
        self.content.parts = parts


class _FakeModels:
    def __init__(self, response):
        self._response = response

    async def generate_content(self, *, model, contents):
        return self._response


class _FakeAio:
    def __init__(self, response):
        self.models = _FakeModels(response)


class _FakeGenaiClient:
    def __init__(self, candidates):
        class _Response:
            pass

        response = _Response()
        response.candidates = candidates
        self.aio = _FakeAio(response)


async def test_generate_returns_inline_image_bytes():
    client = _FakeGenaiClient([_FakeCandidate([_FakePart(b"png-bytes")])])
    gen = GeminiImageGenerator(client=client)
    assert await gen.generate("a red bicycle") == b"png-bytes"


async def test_generate_raises_when_no_image_returned():
    client = _FakeGenaiClient([_FakeCandidate([_FakePart(None)])])
    gen = GeminiImageGenerator(client=client)
    with pytest.raises(ImageGenerationError):
        await gen.generate("a red bicycle")


# --- resolve_images --------------------------------------------------------


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


async def test_resolve_images_fills_only_sections_with_a_prompt():
    spec = PageSpec(
        title="X",
        sections=[
            SectionSpec(type="hero", content={"heading": "Hi", "image_prompt": "a sunrise over hills"}),
            SectionSpec(type="features", content={"heading": "What we do"}),
        ],
    )
    wp = _FakeWp()
    image_gen = _FakeImageGenerator()

    result = await resolve_images(spec, wp, image_generator=image_gen)

    hero, features = result.sections
    assert image_gen.prompts == ["a sunrise over hills"]
    assert "image_prompt" not in hero.content
    assert hero.content["image_url"] == "http://wp.test/1.png"
    assert hero.content["image_id"] == "1"
    assert hero.content["heading"] == "Hi"  # other content untouched
    assert features.content == {"heading": "What we do"}  # never touched, no upload
    assert len(wp.uploads) == 1
    assert wp.uploads[0][0].startswith("hero-")
    assert wp.uploads[0][2] == "image/png"


async def test_resolve_images_is_a_noop_when_no_section_has_a_prompt():
    spec = PageSpec(
        title="X",
        sections=[SectionSpec(type="hero", content={"heading": "Hi"})],
    )
    wp = _FakeWp()

    result = await resolve_images(spec, wp, image_generator=_FakeImageGenerator())

    assert result.sections[0].content == {"heading": "Hi"}
    assert wp.uploads == []


class _FailingImageGenerator:
    async def generate(self, prompt: str) -> bytes:
        raise ImageGenerationError(f"quota exceeded for prompt: {prompt!r}")


async def test_resolve_images_degrades_gracefully_when_generation_fails():
    """A failed image (quota, API error, etc.) must not fail the whole page —
    the section just ends up with no image, same as if no prompt was set."""
    spec = PageSpec(
        title="X",
        sections=[
            SectionSpec(type="hero", content={"heading": "Hi", "image_prompt": "a sunrise"}),
            SectionSpec(type="features", content={"heading": "What we do"}),
        ],
    )
    wp = _FakeWp()

    result = await resolve_images(spec, wp, image_generator=_FailingImageGenerator())

    hero, features = result.sections
    assert hero.content == {"heading": "Hi"}  # prompt dropped, no image_url/image_id
    assert features.content == {"heading": "What we do"}
    assert wp.uploads == []  # never reached the upload step

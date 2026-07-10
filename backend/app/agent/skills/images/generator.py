"""Generate an image from a prompt (Gemini, raw ``google-genai`` SDK).

Uses the raw SDK rather than ``langchain-google-genai`` — image generation
needs direct control over the returned inline image bytes, which LangChain's
Gemini wrapper doesn't expose cleanly. Constructed lazily so importing the
skill doesn't require an API key.
"""

from __future__ import annotations

from typing import Any, Protocol

from google import genai

from app.config import get_settings


class ImageGenerationError(Exception):
    """Raised when Gemini returns no image data for a prompt."""


class ImageGenerator(Protocol):
    async def generate(self, prompt: str) -> bytes: ...


class GeminiImageGenerator:
    def __init__(self, client: Any | None = None):
        self._provided = client
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            settings = get_settings()
            self._client = self._provided or genai.Client(api_key=settings.gemini_api_key)
        return self._client

    async def generate(self, prompt: str) -> bytes:
        settings = get_settings()
        client = self._get_client()
        response = await client.aio.models.generate_content(
            model=settings.gemini_image_model,
            contents=prompt,
        )
        for candidate in response.candidates or []:
            for part in candidate.content.parts or []:
                inline_data = getattr(part, "inline_data", None)
                if inline_data is not None and inline_data.data:
                    return inline_data.data
        raise ImageGenerationError(f"Gemini returned no image data for prompt: {prompt!r}")


def build_image_generator() -> ImageGenerator:
    return GeminiImageGenerator()

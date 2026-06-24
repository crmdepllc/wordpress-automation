# Backend image — FastAPI + LangGraph agent (Python 3.14, uv-managed).
FROM python:3.14-slim

# uv: copy the static binary from the official image (version-stable, no pip).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies first (cached unless the lockfile changes).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Application code.
COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8000

# fastapi run = production uvicorn; reload is handled via the dev override.
CMD ["uv", "run", "fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]

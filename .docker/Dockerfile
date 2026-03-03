FROM python:3.12-slim

# Install uv from the official image — faster and more reliable than pip install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Prevents Python from writing .pyc files and enables unbuffered stdout/stderr
# UV_COMPILE_BYTECODE: pre-compiles .pyc at install time for faster cold starts
# UV_LINK_MODE=copy:  hard-links don't work across Docker layer boundaries
# UV_PYTHON_PREFERENCE: use the system Python already in the image, don't download one
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-system

WORKDIR /app

# Create a non-root user for runtime security
RUN adduser --disabled-password --gecos "" --no-create-home appuser

# ── Dependency layer ─────────────────────────────────────────────────────────
# Copy only the files that define dependencies first.
# This layer is cached and rebuilt only when pyproject.toml or uv.lock changes,
# not every time application source code changes.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

# ── Application source ───────────────────────────────────────────────────────
COPY src/      src/
COPY configs/  configs/
COPY scripts/  scripts/
COPY utils/    utils/
COPY py.typed  ./
# hatchling requires README.md to validate package metadata at build time
COPY README.md ./

# Install the project itself on top of the already-cached dependencies
RUN uv sync --frozen --no-dev

# Ensure the appuser owns the working directory
RUN chown -R appuser:appuser /app

USER appuser

# Activate the virtual environment created by uv
ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "scripts/integration_pipeline.py"]

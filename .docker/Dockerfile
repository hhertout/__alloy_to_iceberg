FROM python:3.12-slim

WORKDIR /app

COPY ./.python-version .
COPY ./pyproject.toml .
COPY ./uv.lock .

RUN pip install --no-cache-dir uv
RUN uv sync --no-cache-dir

COPY . .

CMD ["uv", "run", "python", "scripts/integration_pipeline.py"]
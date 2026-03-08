FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir ".[api]"
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app

EXPOSE 8000

USER appuser

CMD ["uvicorn", "anytask_scraper.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

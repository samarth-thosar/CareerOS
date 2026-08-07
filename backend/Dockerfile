FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e .
RUN playwright install --with-deps chromium

COPY alembic.ini ./
COPY config ./config

EXPOSE 8000

CMD ["uvicorn", "careeros.presentation.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

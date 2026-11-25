FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia contracts + retrieval + backend y los instala como paquetes editables.
COPY contracts/ /app/contracts/
COPY retrieval/ /app/retrieval/
COPY backend/   /app/backend/

RUN pip install --no-cache-dir \
    /app/contracts \
    /app/retrieval \
    /app/backend

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

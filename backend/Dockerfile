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
COPY scripts/   /app/scripts/
# El PDF y el documento de división se incluyen en la imagen porque Docker
# Desktop en macOS puede no tener el repo en su File Sharing. Al pasar a
# modelos reales, Miguel puede remontar resources/ como volumen RO.
COPY resources/ /resources/

RUN pip install --no-cache-dir \
    /app/contracts \
    /app/retrieval \
    /app/backend

# Docling es opcional; si falla en esta plataforma el ingest cae al
# chunker falso (ver retrieval/chunker.py). No bloqueamos el build.
RUN pip install --no-cache-dir docling==2.37.0 || \
    echo "WARN: docling not installed; ingest will use fake chunker"

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

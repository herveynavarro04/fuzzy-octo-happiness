#!/usr/bin/env python
"""Siembra corridas falsas en la tabla runs para probar /admin.

Uso:  python scripts/seed_runs.py [N]      (default 60 corridas en las últimas 24h)
"""
from __future__ import annotations

import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

import asyncio
import asyncpg


async def main(n: int) -> None:
    import os
    dsn = (
        f"postgres://{os.environ.get('POSTGRES_USER','rag')}:"
        f"{os.environ.get('POSTGRES_PASSWORD','rag')}@"
        f"{os.environ.get('POSTGRES_HOST','localhost')}:"
        f"{os.environ.get('POSTGRES_PORT','5432')}/"
        f"{os.environ.get('POSTGRES_DB','rag')}"
    )
    conn = await asyncpg.connect(dsn)
    now = datetime.now(timezone.utc)
    rows = []
    sample_qs = [
        "¿Qué define a un agente LLM?",
        "¿Qué herramientas usan los agentes en el survey?",
        "¿Cómo evalúan los autores los agentes?",
        "¿Cuál es la principal limitación mencionada?",
        "¿Qué trabajo futuro se propone?",
    ]
    for i in range(n):
        mode = random.choice(["chat", "single"])
        cache_hit = random.random() < 0.3 and mode == "single"
        err = None
        if random.random() < 0.05:
            err = "SimulatedError: timeout"
        base = 400 if cache_hit else random.randint(900, 3200)
        rows.append((
            uuid.uuid4(), None, mode,
            random.choice(sample_qs),
            "Respuesta simulada con cita de la sección Intro (p. 2).",
            random.randint(120, 520) if not cache_hit else 0,
            random.randint(60, 240)  if not cache_hit else 0,
            base,
            0 if cache_hit else random.randint(80, 600),
            cache_hit,
            "fake",
            [], err,
            now - timedelta(minutes=random.randint(1, 60 * 23)),
        ))
    await conn.executemany(
        """
        INSERT INTO runs
        (id, conversation_id, mode, question, answer,
         input_tokens, output_tokens, latency_ms, retrieval_ms,
         cache_hit, model, retrieved_chunk_ids, error, created_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
        """,
        rows,
    )
    await conn.close()
    print(f"inserted {n} fake runs")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 60))

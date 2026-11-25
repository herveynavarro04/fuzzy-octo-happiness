"""Pool de Postgres y escrituras/consultas sobre runs/conversations/messages."""
from __future__ import annotations

import os
from typing import Any
from uuid import UUID

import asyncpg

_POOL: asyncpg.Pool | None = None


def _dsn() -> str:
    user = os.environ["POSTGRES_USER"]
    pwd  = os.environ["POSTGRES_PASSWORD"]
    db   = os.environ["POSTGRES_DB"]
    host = os.environ.get("POSTGRES_HOST", "postgres")
    port = os.environ.get("POSTGRES_PORT", "5432")
    return f"postgres://{user}:{pwd}@{host}:{port}/{db}"


async def startup() -> None:
    global _POOL
    _POOL = await asyncpg.create_pool(_dsn(), min_size=1, max_size=5)


async def shutdown() -> None:
    global _POOL
    if _POOL is not None:
        await _POOL.close()
        _POOL = None


async def pool() -> asyncpg.Pool:
    assert _POOL is not None, "db not initialized"
    return _POOL


# ------------------------ writes ------------------------

async def ensure_conversation(session_id: str | None) -> UUID:
    p = await pool()
    async with p.acquire() as conn:
        if session_id:
            row = await conn.fetchrow(
                "UPDATE conversations SET last_seen=now() WHERE id=$1 RETURNING id",
                UUID(session_id),
            )
            if row:
                return row["id"]
        row = await conn.fetchrow(
            "INSERT INTO conversations DEFAULT VALUES RETURNING id"
        )
        return row["id"]


async def append_message(conv_id: UUID, role: str, content: str) -> None:
    p = await pool()
    async with p.acquire() as conn:
        await conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES ($1,$2,$3)",
            conv_id, role, content,
        )


async def insert_run(
    *,
    conversation_id: UUID | None,
    mode: str,
    question: str,
    answer: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    retrieval_ms: int,
    cache_hit: bool,
    model: str,
    retrieved_chunk_ids: list[str],
    error: str | None,
) -> UUID:
    p = await pool()
    async with p.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO runs (
                conversation_id, mode, question, answer,
                input_tokens, output_tokens, latency_ms, retrieval_ms,
                cache_hit, model, retrieved_chunk_ids, error
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            RETURNING id
            """,
            conversation_id, mode, question, answer,
            input_tokens, output_tokens, latency_ms, retrieval_ms,
            cache_hit, model, retrieved_chunk_ids, error,
        )
        return row["id"]


# ------------------------ reads (/admin) ------------------------

async def stats() -> dict[str, Any]:
    p = await pool()
    async with p.acquire() as conn:
        totals = await conn.fetchrow(
            """
            SELECT
                COUNT(*)                                                 AS runs,
                COALESCE(SUM(input_tokens), 0)                           AS input_tokens,
                COALESCE(SUM(output_tokens), 0)                          AS output_tokens,
                COALESCE(AVG(latency_ms), 0)::INT                        AS avg_latency_ms,
                COALESCE(
                    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms),
                    0
                )::INT                                                   AS p95_latency_ms,
                COALESCE(AVG(retrieval_ms), 0)::INT                      AS avg_retrieval_ms,
                COALESCE(AVG(CASE WHEN cache_hit THEN 1.0 ELSE 0.0 END), 0)
                                                                         AS cache_hit_rate,
                COUNT(*) FILTER (WHERE error IS NOT NULL)                AS errors
            FROM runs
            """
        )
        activity = await conn.fetch(
            """
            SELECT date_trunc('hour', created_at) AS hour, COUNT(*) AS n
            FROM runs
            WHERE created_at > now() - interval '24 hours'
            GROUP BY 1 ORDER BY 1
            """
        )
    return {
        **dict(totals),
        "activity": [{"hour": r["hour"].isoformat(), "n": r["n"]} for r in activity],
    }


async def recent_runs(limit: int = 50) -> list[dict[str, Any]]:
    p = await pool()
    async with p.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, mode, question, answer, input_tokens, output_tokens,
                   latency_ms, retrieval_ms, cache_hit, model, error, created_at
            FROM runs ORDER BY created_at DESC LIMIT $1
            """,
            limit,
        )
    return [
        {
            **{k: (str(v) if k in ("id",) else v) for k, v in dict(r).items()},
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]

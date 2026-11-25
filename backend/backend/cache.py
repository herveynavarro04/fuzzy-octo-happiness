"""Redis: historial de chat con TTL, cache de respuestas single, rate limit por IP."""
from __future__ import annotations

import json
import os
import time
from typing import Optional

import redis.asyncio as redis

_CLIENT: redis.Redis | None = None

HISTORY_TTL = 60 * 60 * 24      # 24h
ANSWER_TTL  = 60 * 10            # 10 min
RATE_LIMIT  = 30                 # req/min por IP
RATE_WINDOW = 60


async def startup() -> None:
    global _CLIENT
    _CLIENT = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    await _CLIENT.ping()


async def shutdown() -> None:
    global _CLIENT
    if _CLIENT is not None:
        await _CLIENT.close()
        _CLIENT = None


def client() -> redis.Redis:
    assert _CLIENT is not None, "redis not initialized"
    return _CLIENT


# --------- chat history ---------

async def push_history(session_id: str, role: str, content: str) -> None:
    c = client()
    key = f"chat:{session_id}"
    await c.rpush(key, json.dumps({"role": role, "content": content}))
    await c.ltrim(key, -20, -1)       # últimos 20 turnos
    await c.expire(key, HISTORY_TTL)


async def read_history(session_id: str) -> list[dict]:
    c = client()
    raw = await c.lrange(f"chat:{session_id}", 0, -1)
    return [json.loads(x) for x in raw]


# --------- single-mode cache ---------

def _answer_key(question: str) -> str:
    return f"answer:single:{question.strip().lower()}"


async def get_cached_answer(question: str) -> Optional[dict]:
    c = client()
    raw = await c.get(_answer_key(question))
    return json.loads(raw) if raw else None


async def put_cached_answer(question: str, payload: dict) -> None:
    c = client()
    await c.setex(_answer_key(question), ANSWER_TTL, json.dumps(payload))


# --------- rate limit ---------

async def rate_limit_ok(ip: str) -> bool:
    c = client()
    key = f"rl:{ip}:{int(time.time()) // RATE_WINDOW}"
    cur = await c.incr(key)
    if cur == 1:
        await c.expire(key, RATE_WINDOW + 5)
    return cur <= RATE_LIMIT

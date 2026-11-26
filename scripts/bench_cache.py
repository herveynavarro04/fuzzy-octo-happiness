#!/usr/bin/env python
"""
Compara latencia con y sin cache de Redis.

Para N preguntas:
  1. Limpia el cache (SCAN + DEL de "answer:single:*").
  2. Primera pasada: cache miss garantizado.
  3. Segunda pasada: cache hit (si el modo es single).
  Imprime avg y p95 de ambas pasadas como tabla markdown.

Uso:
    python scripts/bench_cache.py --n 10 --base http://localhost:8000

Requiere stack arriba y, para el flush, REDIS_URL alcanzable desde donde se corre.
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time

import httpx
import redis


QUESTIONS = [
    "¿Cuál es el título del artículo?",
    "¿Quiénes son los autores?",
    "¿En qué revista se publicó?",
    "¿Qué define un agente LLM según el artículo?",
    "¿Qué herramientas externas se mencionan?",
    "¿Qué métricas de evaluación proponen?",
    "¿Qué benchmarks usan los autores?",
    "¿Cuáles son las limitaciones principales?",
    "¿Qué trabajo futuro sugieren?",
    "¿Qué prompting se menciona como alternativa?",
]


def _flush_cache(url: str) -> int:
    r = redis.Redis.from_url(url, decode_responses=True)
    deleted = 0
    for key in r.scan_iter(match="answer:single:*", count=200):
        r.delete(key)
        deleted += 1
    return deleted


def _run(client: httpx.Client, qs: list[str]) -> list[float]:
    out: list[float] = []
    for q in qs:
        t = time.perf_counter()
        r = client.post("/ask", json={"question": q, "mode": "single"})
        r.raise_for_status()
        out.append((time.perf_counter() - t) * 1000.0)
    return out


def _p95(xs: list[float]) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    i = int(round(0.95 * (len(xs) - 1)))
    return xs[i]


def main(base: str, n: int, redis_url: str) -> int:
    qs = QUESTIONS[:n]
    deleted = _flush_cache(redis_url)
    print(f"flushed {deleted} answer:single:* keys")

    with httpx.Client(base_url=base, timeout=60.0) as client:
        miss = _run(client, qs)
        hit  = _run(client, qs)

    def row(label: str, xs: list[float]) -> str:
        return f"| {label:<13} | {statistics.mean(xs):>7.1f} | {_p95(xs):>7.1f} |"

    print(f"\n| Escenario     | avg ms | p95 ms |")
    print(  "| ------------- | ------ | ------ |")
    print(row("Sin caché",       miss))
    print(row("Con caché",       hit))
    print(f"\nSobre {len(qs)} preguntas.")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base",  default="http://localhost:8000")
    p.add_argument("--n",     type=int, default=10)
    p.add_argument("--redis", default=os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    args = p.parse_args()
    sys.exit(main(args.base, args.n, args.redis))

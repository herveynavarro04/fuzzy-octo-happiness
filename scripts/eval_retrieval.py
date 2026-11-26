#!/usr/bin/env python
"""
Evaluación de recuperación comparando 4 configuraciones:

    1. BM25 solo
    2. Vectores solos (kNN)
    3. Híbrida (BM25 || kNN con RRF)  <- la que usa /ask por defecto
    4. Híbrida + rerank

Lee data/eval_questions.jsonl ({question, expected_section, expected_page}).
Mide Hit@k y MRR@k. Imprime una tabla markdown lista para pegar en el README.

Uso (dentro del contenedor api, con stack arriba):
    docker compose -f infra/docker-compose.yml exec api python /app/scripts/eval_retrieval.py
    # con FAKE_MODELS=true: los vectores son determinísticos pero no semánticos,
    # así que estos números son para la plomería, no para calidad.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Iterable

from opensearchpy import OpenSearch

from retrieval.clients import EmbeddingsClient, RerankClient
from retrieval.retrieve import _bm25, _knn, _rrf
from retrieval.settings import get_settings


def _is_hit(section_exp: str, page_exp: int, hits) -> int:
    es = (section_exp or "").lower().strip()
    for h in hits:
        src = h["_source"] if isinstance(h, dict) and "_source" in h else h
        if es and es in (src.get("section", "") or "").lower():
            return 1
        if page_exp and int(src.get("page", 0)) == page_exp:
            return 1
    return 0


def _rr(section_exp: str, page_exp: int, ordered_sources) -> float:
    """Reciprocal rank. ordered_sources is a list of _source dicts in rank order."""
    es = (section_exp or "").lower().strip()
    for rank, src in enumerate(ordered_sources, start=1):
        if es and es in (src.get("section", "") or "").lower():
            return 1.0 / rank
        if page_exp and int(src.get("page", 0)) == page_exp:
            return 1.0 / rank
    return 0.0


def _bm25_ordered(query: str, k: int) -> list[dict]:
    s = get_settings()
    cli = OpenSearch(hosts=[s.opensearch_url], timeout=30)
    return [h["_source"] | {"_id": h["_id"]} for h in _bm25(cli, s.opensearch_index, query, k)]


def _knn_ordered(query: str, k: int) -> list[dict]:
    s = get_settings()
    cli = OpenSearch(hosts=[s.opensearch_url], timeout=30)
    vec = EmbeddingsClient(s).embed([query], mode="query")[0]
    return [h["_source"] | {"_id": h["_id"]} for h in _knn(cli, s.opensearch_index, vec, k)]


def _hybrid_ordered(query: str, k: int) -> list[dict]:
    s = get_settings()
    cli = OpenSearch(hosts=[s.opensearch_url], timeout=30)
    vec = EmbeddingsClient(s).embed([query], mode="query")[0]
    bm   = _bm25(cli, s.opensearch_index, query, 20)
    knn  = _knn(cli, s.opensearch_index, vec, 20)
    fused = _rrf(bm, knn)
    return [src for (_id, _score, src) in fused[:k]]


def _hybrid_rerank_ordered(query: str, k: int) -> list[dict]:
    s = get_settings()
    pool = _hybrid_ordered(query, k * 4)
    if not pool:
        return []
    scores = RerankClient(s).score(query, [p["text"] for p in pool])
    reranked = sorted(zip(pool, scores), key=lambda t: t[1], reverse=True)
    return [p for p, _ in reranked[:k]]


CONFIGS: dict[str, Callable[[str, int], list[dict]]] = {
    "BM25":              _bm25_ordered,
    "Vectores":          _knn_ordered,
    "Híbrida (RRF)":     _hybrid_ordered,
    "Híbrida + rerank":  _hybrid_rerank_ordered,
}


def eval_file(path: Path, k: int) -> dict[str, tuple[float, float, int]]:
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    out: dict[str, tuple[float, float, int]] = {}
    for name, fn in CONFIGS.items():
        hits = 0
        mrr_sum = 0.0
        for q in rows:
            ordered = fn(q["question"], k)
            hits   += _is_hit(q.get("expected_section", ""), int(q.get("expected_page", 0) or 0), ordered)
            mrr_sum += _rr(q.get("expected_section", ""), int(q.get("expected_page", 0) or 0), ordered)
        n = len(rows) or 1
        out[name] = (hits / n, mrr_sum / n, n)
    return out


def print_markdown(results: dict[str, tuple[float, float, int]], k: int) -> None:
    print(f"\n| Configuración       | Hit@{k} | MRR@{k} |")
    print(  "| ------------------- | ------ | ------ |")
    for name, (hit, mrr, n) in results.items():
        print(f"| {name:<19} | {hit:.2%} | {mrr:.3f} |")
    n = next(iter(results.values()))[2]
    print(f"\nSobre {n} preguntas.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("path", nargs="?", default="data/eval_questions.jsonl")
    p.add_argument("-k", type=int, default=5)
    args = p.parse_args()
    path = Path(args.path)
    if not path.exists():
        print(f"missing {path}", file=sys.stderr)
        sys.exit(2)
    print_markdown(eval_file(path, args.k), args.k)

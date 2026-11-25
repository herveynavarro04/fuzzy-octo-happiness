"""
retrieve(query, k) = BM25 ∥ kNN fusionados con RRF; rerank opcional; caché Redis.

Contrato:
    retrieve(query: str, k: int = 5) -> list[Chunk]
"""
from __future__ import annotations

import json
import logging
from typing import Any

import redis
from opensearchpy import OpenSearch

from contracts import Chunk
from retrieval.clients import EmbeddingsClient, RerankClient
from retrieval.settings import get_settings

log = logging.getLogger("retrieve")

_RRF_K = 60
_POOL = 20  # candidatos por lado antes de fusionar


def _os() -> OpenSearch:
    return OpenSearch(hosts=[get_settings().opensearch_url], timeout=30)


def _redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)


def _bm25(cli: OpenSearch, index: str, query: str, size: int) -> list[dict[str, Any]]:
    body = {"size": size, "query": {"match": {"text": query}}}
    res = cli.search(index=index, body=body)
    return res["hits"]["hits"]


def _knn(cli: OpenSearch, index: str, vector: list[float], size: int) -> list[dict[str, Any]]:
    body = {"size": size, "query": {"knn": {"vector": {"vector": vector, "k": size}}}}
    res = cli.search(index=index, body=body)
    return res["hits"]["hits"]


def _rrf(*rankings: list[dict[str, Any]], k: int = _RRF_K) -> list[tuple[str, float, dict]]:
    """Reciprocal Rank Fusion."""
    scores: dict[str, float] = {}
    sources: dict[str, dict] = {}
    for hits in rankings:
        for rank, h in enumerate(hits):
            _id = h["_id"]
            scores[_id] = scores.get(_id, 0.0) + 1.0 / (k + rank + 1)
            sources.setdefault(_id, h["_source"] | {"_id": _id})
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [(i, s, sources[i]) for i, s in ordered]


def _hit_to_chunk(hit_id: str, src: dict, score: float) -> Chunk:
    return Chunk(
        id=hit_id,
        text=src.get("text", ""),
        section=src.get("section", ""),
        page=int(src.get("page", 0)),
        kind=src.get("kind", "text"),
        score=float(score),
    )


def retrieve(query: str, k: int = 5) -> list[Chunk]:
    s = get_settings()

    cache_key = f"retrieve:{s.embed_model}:{s.use_reranker}:{k}:{query}"
    r = _redis()
    try:
        cached = r.get(cache_key)
        if cached:
            data = json.loads(cached)
            return [Chunk.model_validate(c) for c in data]
    except Exception as e:  # cache nunca bloquea
        log.warning("redis get failed: %s", e)

    emb = EmbeddingsClient(s)
    qvec = emb.embed([query], mode="query")[0]

    cli = _os()
    bm25_hits = _bm25(cli, s.opensearch_index, query, _POOL)
    knn_hits  = _knn(cli, s.opensearch_index, qvec, _POOL)

    fused = _rrf(bm25_hits, knn_hits)
    pool = fused[: max(k * 4, 10)]

    if s.use_reranker and pool:
        texts = [src["text"] for _, _, src in pool]
        scores = RerankClient(s).score(query, texts)
        pool = sorted(
            [(i, sc, src) for (i, _, src), sc in zip(pool, scores)],
            key=lambda t: t[1],
            reverse=True,
        )

    chunks = [_hit_to_chunk(i, src, sc) for (i, sc, src) in pool[:k]]

    try:
        r.setex(cache_key, 3600, json.dumps([c.model_dump() for c in chunks]))
    except Exception as e:
        log.warning("redis set failed: %s", e)

    return chunks

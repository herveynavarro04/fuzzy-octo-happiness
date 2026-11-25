"""
Índice OpenSearch con BM25 + knn_vector (cosine), dimensión EMBED_DIM.
"""
from __future__ import annotations

import logging
from typing import Iterable

from opensearchpy import OpenSearch, helpers

from retrieval.chunker import RawChunk
from retrieval.settings import get_settings

log = logging.getLogger("index")


def _client() -> OpenSearch:
    s = get_settings()
    return OpenSearch(hosts=[s.opensearch_url], timeout=30)


def ensure_index(*, recreate: bool = False) -> None:
    s = get_settings()
    cli = _client()
    if cli.indices.exists(index=s.opensearch_index):
        if not recreate:
            return
        cli.indices.delete(index=s.opensearch_index)
    body = {
        "settings": {
            "index": {
                "knn": True,
                "number_of_shards": 1,
                "number_of_replicas": 0,
            }
        },
        "mappings": {
            "properties": {
                "text":    {"type": "text"},
                "section": {"type": "keyword"},
                "page":    {"type": "integer"},
                "kind":    {"type": "keyword"},
                "vector": {
                    "type": "knn_vector",
                    "dimension": s.embed_dim,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "lucene",
                    },
                },
            }
        },
    }
    cli.indices.create(index=s.opensearch_index, body=body)
    log.info("created index %s (dim=%d)", s.opensearch_index, s.embed_dim)


def bulk_load(chunks: Iterable[RawChunk], vectors: dict[str, list[float]]) -> int:
    s = get_settings()
    cli = _client()

    def _actions():
        for c in chunks:
            vec = vectors.get(c.id)
            if vec is None:
                continue
            yield {
                "_op_type": "index",
                "_index": s.opensearch_index,
                "_id": c.id,
                "_source": {
                    "text": c.text,
                    "section": c.section,
                    "page": c.page,
                    "kind": c.kind,
                    "vector": vec,
                },
            }

    ok, _ = helpers.bulk(cli, _actions(), refresh=True)
    return ok

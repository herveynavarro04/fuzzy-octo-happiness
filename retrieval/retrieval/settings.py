from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    fake_models: bool
    paper_path: str

    embed_url: str
    embed_model: str
    embed_dim: int

    rerank_url: str
    rerank_model: str
    use_reranker: bool

    vlm_url: str
    vlm_model: str

    ollama_url: str
    llm_model: str

    opensearch_url: str
    opensearch_index: str

    redis_url: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        fake_models=_bool("FAKE_MODELS", True),
        paper_path=os.environ.get("PAPER_PATH", "resources/article.pdf"),
        embed_url=os.environ.get("EMBED_URL", "http://vllm-embed:8000/v1"),
        embed_model=os.environ.get("EMBED_MODEL", "nvidia/Nemotron-3-Embed-1B-BF16"),
        embed_dim=int(os.environ.get("EMBED_DIM", "1024")),
        rerank_url=os.environ.get("RERANK_URL", "http://vllm-rerank:8000/v1"),
        rerank_model=os.environ.get("RERANK_MODEL", "nvidia/llama-nemotron-rerank-1b-v2"),
        use_reranker=_bool("USE_RERANKER", True),
        vlm_url=os.environ.get("VLM_URL", "http://vllm-vlm:8000/v1"),
        vlm_model=os.environ.get("VLM_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct"),
        ollama_url=os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434"),
        llm_model=os.environ.get("LLM_MODEL", "nemotron-3-nano:4b"),
        opensearch_url=os.environ.get("OPENSEARCH_URL", "http://opensearch:9200"),
        opensearch_index=os.environ.get("OPENSEARCH_INDEX", "paper_chunks"),
        redis_url=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
    )

"""
Clientes HTTP a los servicios de modelos.

- EmbeddingsClient: API /v1/embeddings compatible con OpenAI (vLLM).
  Antepone 'query: ' o 'passage: ' según el modo (Nemotron-Embed),
  recorta a EMBED_DIM y re-normaliza, como permite la model card.
- RerankClient: API /v1/score (classifier head) de vLLM para el reranker.
- VLMClient: chat completions con imagen base64 para describir figuras.

Si FAKE_MODELS=true, todos los clientes son deterministas y no llaman red.
"""
from __future__ import annotations

import base64
import hashlib
import math
from pathlib import Path
from typing import Literal

import httpx
import numpy as np

from retrieval.settings import Settings, get_settings


# ------------------------------- embeddings -------------------------------

def _fake_embed(text: str, dim: int) -> list[float]:
    """Vector determinista a partir del hash del texto, L2-normalizado."""
    rng = np.random.default_rng(
        int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
    )
    v = rng.standard_normal(dim).astype(np.float32)
    v /= np.linalg.norm(v) + 1e-12
    return v.tolist()


class EmbeddingsClient:
    def __init__(self, settings: Settings | None = None, *, client: httpx.Client | None = None):
        self.s = settings or get_settings()
        self._client = client

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(base_url=self.s.embed_url, timeout=60.0)
        return self._client

    def embed(self, texts: list[str], *, mode: Literal["query", "passage"]) -> list[list[float]]:
        if not texts:
            return []
        prefix = f"{mode}: "
        inputs = [prefix + t for t in texts]
        if self.s.fake_models:
            return [_fake_embed(t, self.s.embed_dim) for t in inputs]

        resp = self._http().post(
            "/embeddings",
            json={"model": self.s.embed_model, "input": inputs, "encoding_format": "float"},
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        out: list[list[float]] = []
        for item in data:
            v = np.asarray(item["embedding"], dtype=np.float32)
            if v.shape[0] > self.s.embed_dim:
                v = v[: self.s.embed_dim]
            v /= np.linalg.norm(v) + 1e-12  # renormalizar tras recortar
            out.append(v.tolist())
        return out


# --------------------------------- reranker -------------------------------

class RerankClient:
    """
    Usa /v1/score de vLLM. La model card del reranker especifica un chat
    template para scoring; vLLM lo aplica por detrás cuando se levanta con
    --task score. El cliente solo manda (query, documents) y lee 'score'.
    """

    def __init__(self, settings: Settings | None = None, *, client: httpx.Client | None = None):
        self.s = settings or get_settings()
        self._client = client

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(base_url=self.s.rerank_url, timeout=60.0)
        return self._client

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        if self.s.fake_models:
            # Falso estable: mantiene el orden actual (score decreciente).
            return [1.0 - i * 1e-3 for i in range(len(documents))]

        resp = self._http().post(
            "/score",
            json={"model": self.s.rerank_model, "text_1": query, "text_2": documents},
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return [float(it["score"]) for it in data]


# ------------------------------------ VLM ---------------------------------

class VLMClient:
    """Describe figuras con Qwen2.5-VL vía chat completions con imagen."""

    def __init__(self, settings: Settings | None = None, *, client: httpx.Client | None = None):
        self.s = settings or get_settings()
        self._client = client

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(base_url=self.s.vlm_url, timeout=120.0)
        return self._client

    def describe(self, image_path: str | Path, *, hint: str = "") -> str:
        p = Path(image_path)
        if self.s.fake_models:
            return f"[fake-figure-description] {p.stem} ({hint or 'figura'})"

        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        prompt = (
            "Describe esta figura de un paper académico con el máximo detalle "
            "útil para búsqueda semántica: ejes, categorías, tendencias y "
            "cualquier texto visible. 3 a 6 frases."
        )
        if hint:
            prompt += f" Contexto adicional: {hint}."
        resp = self._http().post(
            "/chat/completions",
            json={
                "model": self.s.vlm_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{b64}"},
                            },
                        ],
                    }
                ],
                "max_tokens": 400,
                "temperature": 0.2,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


__all__ = ["EmbeddingsClient", "RerankClient", "VLMClient"]

#!/usr/bin/env python
"""
Descarga los tres modelos de Hugging Face a la caché compartida que montan
los contenedores (volumen `hfcache` en el compose -> HF_HOME=/models).

Uso en la Mac de Miguel:

    export HUGGING_FACE_HUB_TOKEN=hf_xxx            # si los modelos lo requieren
    export HF_HOME=$PWD/data/hf_cache               # o la ruta del volumen
    python scripts/download_models.py               # los tres
    python scripts/download_models.py embed rerank  # subset

En el contenedor:

    docker compose -f infra/docker-compose.yml run --rm vllm-embed \
        python /app/scripts/download_models.py embed
"""
from __future__ import annotations

import os
import sys

from huggingface_hub import snapshot_download

MODELS = {
    "embed":  "nvidia/Nemotron-3-Embed-1B-BF16",
    "rerank": "nvidia/llama-nemotron-rerank-1b-v2",
    "vlm":    "Qwen/Qwen2.5-VL-7B-Instruct",
}


def main(targets: list[str]) -> None:
    cache = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
    print(f"[download] HF_HOME = {cache}")
    for key in targets:
        repo = MODELS[key]
        print(f"[download] {key} -> {repo}")
        path = snapshot_download(repo_id=repo, cache_dir=cache)
        print(f"[download] OK {key} at {path}")


if __name__ == "__main__":
    args = sys.argv[1:] or list(MODELS.keys())
    unknown = [a for a in args if a not in MODELS]
    if unknown:
        print(f"Unknown targets: {unknown}. Choose from {list(MODELS)}", file=sys.stderr)
        sys.exit(2)
    main(args)

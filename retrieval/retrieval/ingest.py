"""
Pipeline de ingesta en 4 etapas, corribles por separado:

  python -m retrieval.ingest chunks        # PDF -> data/chunks.jsonl + data/figures/
  python -m retrieval.ingest figures       # describe figuras con VLM -> actualiza chunks.jsonl
  python -m retrieval.ingest embeddings    # calcula vectores -> data/embeddings.jsonl
  python -m retrieval.ingest load          # crea índice OpenSearch y bulk-load
  python -m retrieval.ingest all           # las 4 en orden

Con FAKE_MODELS=true ni los embeddings ni la VLM llaman red.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from retrieval.chunker import RawChunk, read_chunks, run_chunker
from retrieval.clients import EmbeddingsClient, VLMClient
from retrieval.settings import get_settings

log = logging.getLogger("ingest")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")


DATA_DIR    = Path("data")
CHUNKS_PATH = DATA_DIR / "chunks.jsonl"
EMBEDS_PATH = DATA_DIR / "embeddings.jsonl"
FIGURES_DIR = DATA_DIR / "figures"


# ------------------------------- stages -------------------------------

def stage_chunks() -> None:
    s = get_settings()
    pdf = Path(s.paper_path)
    if not pdf.exists():
        raise SystemExit(f"PAPER_PATH not found: {pdf}")
    n = run_chunker(pdf, CHUNKS_PATH, FIGURES_DIR)
    log.info("wrote %d chunks -> %s", n, CHUNKS_PATH)


def stage_figures() -> None:
    if not CHUNKS_PATH.exists():
        raise SystemExit(f"run 'chunks' first; {CHUNKS_PATH} missing")
    vlm = VLMClient()
    chunks = read_chunks(CHUNKS_PATH)
    updated = 0
    for c in chunks:
        if c.kind != "figure":
            continue
        img = FIGURES_DIR / f"{c.id}.png"
        # fallback: cualquier figure_XXX.png suelta
        if not img.exists():
            candidates = sorted(FIGURES_DIR.glob("figure_*.png"))
            if not candidates:
                continue
            img = candidates[updated % len(candidates)]
        c.text = vlm.describe(img, hint=c.section)
        updated += 1
    _write_chunks(chunks, CHUNKS_PATH)
    log.info("described %d figures", updated)


def stage_embeddings() -> None:
    if not CHUNKS_PATH.exists():
        raise SystemExit(f"run 'chunks' first; {CHUNKS_PATH} missing")
    emb = EmbeddingsClient()
    chunks = read_chunks(CHUNKS_PATH)
    texts = [c.text for c in chunks]
    # batch pequeño para no saturar vLLM con CPU
    batch = 16
    with EMBEDS_PATH.open("w", encoding="utf-8") as f:
        for i in range(0, len(texts), batch):
            vecs = emb.embed(texts[i : i + batch], mode="passage")
            for c, v in zip(chunks[i : i + batch], vecs):
                f.write(json.dumps({"id": c.id, "vector": v}) + "\n")
    log.info("wrote %d embeddings -> %s", len(chunks), EMBEDS_PATH)


def stage_load() -> None:
    from retrieval.index import ensure_index, bulk_load

    if not CHUNKS_PATH.exists() or not EMBEDS_PATH.exists():
        raise SystemExit("run 'chunks' and 'embeddings' first")
    chunks = read_chunks(CHUNKS_PATH)
    vectors: dict[str, list[float]] = {}
    with EMBEDS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            vectors[d["id"]] = d["vector"]

    ensure_index(recreate=True)
    n = bulk_load(chunks, vectors)
    log.info("loaded %d chunks into OpenSearch", n)


# ------------------------------- helpers -------------------------------

def _write_chunks(chunks: list[RawChunk], path: Path) -> None:
    from dataclasses import asdict
    with path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")


STAGES = {
    "chunks":     stage_chunks,
    "figures":    stage_figures,
    "embeddings": stage_embeddings,
    "load":       stage_load,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=[*STAGES, "all"])
    args = parser.parse_args()
    DATA_DIR.mkdir(exist_ok=True)
    stages = list(STAGES) if args.stage == "all" else [args.stage]
    for st in stages:
        log.info("=== stage: %s ===", st)
        STAGES[st]()


if __name__ == "__main__":
    sys.exit(main())

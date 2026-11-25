"""
Ingesta de PDF con Docling.

Produce chunks con section, page, kind (text|table|figure). Tablas en markdown.
Extrae figuras a disco. Escribe chunks.jsonl (sin vectores) y figures/.

Si Docling no está instalado o falla por memoria, se levanta DoclingUnavailable
y la ingesta cae a un 'fake chunker' que genera chunks mínimos del PDF usando
sólo el nombre de archivo, para que FAKE_MODELS pueda seguir.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Literal

log = logging.getLogger(__name__)


ChunkKind = Literal["text", "table", "figure"]


@dataclass
class RawChunk:
    id: str
    text: str
    section: str
    page: int
    kind: ChunkKind


class DoclingUnavailable(RuntimeError):
    pass


def _safe_caption(item, default: str) -> str:
    """docling-core expone `caption_text` como método en versiones recientes."""
    val = getattr(item, "caption_text", None)
    if callable(val):
        try:
            val = val()
        except Exception:
            val = None
    if isinstance(val, str) and val.strip():
        return val.strip()
    return default


# ----------------------------- Docling -----------------------------

def _docling_convert(pdf_path: Path):
    try:
        from docling.document_converter import DocumentConverter
    except Exception as e:  # pragma: no cover
        raise DoclingUnavailable(f"docling not importable: {e}") from e
    conv = DocumentConverter()
    return conv.convert(str(pdf_path))


def _iter_docling_chunks(result) -> Iterable[RawChunk]:
    """
    Usa HierarchicalChunker + section/page si están disponibles.
    Normaliza tablas a markdown.
    """
    try:
        from docling.chunking import HierarchicalChunker
    except Exception as e:  # pragma: no cover
        raise DoclingUnavailable(f"docling chunker missing: {e}") from e

    doc = result.document
    chunker = HierarchicalChunker()
    for ch in chunker.chunk(doc):
        text = (getattr(ch, "text", None) or "").strip()
        if not text:
            continue
        section = ""
        page = 0
        headings = getattr(getattr(ch, "meta", None), "headings", None) or []
        if headings:
            section = " / ".join(h for h in headings if h)
        # best-effort page number
        for item in getattr(getattr(ch, "meta", None), "doc_items", []) or []:
            for prov in getattr(item, "prov", []) or []:
                if getattr(prov, "page_no", None):
                    page = int(prov.page_no)
                    break
            if page:
                break
        yield RawChunk(
            id=str(uuid.uuid4()),
            text=text,
            section=section,
            page=page,
            kind="text",
        )

    # Tablas como markdown
    for table in getattr(doc, "tables", []) or []:
        try:
            md = table.export_to_markdown()
        except Exception:
            continue
        if not md.strip():
            continue
        page = 0
        for prov in getattr(table, "prov", []) or []:
            if getattr(prov, "page_no", None):
                page = int(prov.page_no)
                break
        yield RawChunk(
            id=str(uuid.uuid4()),
            text=md,
            section=_safe_caption(table, "Table"),
            page=page,
            kind="table",
        )


def extract_figures(result, out_dir: Path) -> list[RawChunk]:
    """Extrae imágenes de figuras; el texto es un placeholder — lo llena VLM después."""
    out_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[RawChunk] = []
    doc = result.document
    for i, pic in enumerate(getattr(doc, "pictures", []) or []):
        try:
            img = pic.image.pil_image if hasattr(pic, "image") and pic.image else None
        except Exception:
            img = None
        if img is None:
            continue
        img_path = out_dir / f"figure_{i:03d}.png"
        img.save(img_path)
        page = 0
        for prov in getattr(pic, "prov", []) or []:
            if getattr(prov, "page_no", None):
                page = int(prov.page_no)
                break
        caption = _safe_caption(pic, f"Figure {i+1}")
        chunks.append(RawChunk(
            id=str(uuid.uuid4()),
            text=f"[figure placeholder] {caption}",
            section=caption,
            page=page,
            kind="figure",
        ))
    return chunks


# ----------------------------- Fake chunker -----------------------------

def _fake_chunks(pdf_path: Path) -> list[RawChunk]:
    """
    Si Docling no está disponible (OOM, etc.), devolvemos chunks mínimos
    para que la ingesta/retrieve sigan funcionando con FAKE_MODELS.
    """
    name = pdf_path.stem
    base = [
        ("Abstract", 1,
         f"Este es un chunk falso del artículo '{name}'. "
         "Resume en una o dos frases el objetivo general del survey."),
        ("Introduction", 2,
         "Chunk falso de introducción: contexto, motivación y alcance del trabajo."),
        ("Methods", 4,
         "Chunk falso de métodos: pipeline, modelos y evaluación."),
        ("Results", 7,
         "Chunk falso de resultados: tablas y gráficas resumen."),
        ("Discussion", 10,
         "Chunk falso de discusión: limitaciones y trabajo futuro."),
        ("Conclusion", 12,
         "Chunk falso de conclusión: aporte principal y siguientes pasos."),
    ]
    return [
        RawChunk(id=str(uuid.uuid4()), text=t, section=s, page=p, kind="text")
        for (s, p, t) in base
    ]


# ----------------------------- IO -----------------------------

def run_chunker(pdf_path: Path, chunks_out: Path, figures_dir: Path) -> int:
    """Corre Docling, extrae figuras y escribe chunks.jsonl. Devuelve #chunks."""
    chunks_out.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = _docling_convert(pdf_path)
        chunks = list(_iter_docling_chunks(result))
        chunks += extract_figures(result, figures_dir)
        log.info("docling ok: %d chunks", len(chunks))
    except DoclingUnavailable as e:
        log.warning("docling unavailable, using fake chunker: %s", e)
        chunks = _fake_chunks(pdf_path)
    except Exception as e:
        log.exception("docling failed (%s); falling back to fake chunker", e)
        chunks = _fake_chunks(pdf_path)

    with chunks_out.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    return len(chunks)


def read_chunks(chunks_path: Path) -> list[RawChunk]:
    out: list[RawChunk] = []
    with chunks_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            out.append(RawChunk(**d))
    return out

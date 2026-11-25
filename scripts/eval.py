#!/usr/bin/env python
"""
Evaluación de recuperación: Hit@k.

Lee data/eval_questions.jsonl donde cada línea es:
    {"question": "...", "expected_section": "Intro", "expected_page": 2}

Para cada pregunta, pide k chunks a retrieve() y marca hit si algún chunk
coincide con la sección esperada (contiene substring, case-insensitive)
o con la página esperada.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from retrieval.retrieve import retrieve


def _hit(expected_section: str, expected_page: int, chunks) -> bool:
    es = (expected_section or "").lower().strip()
    for c in chunks:
        if es and es in (c.section or "").lower():
            return True
        if expected_page and int(c.page) == int(expected_page):
            return True
    return False


def main(path: str = "data/eval_questions.jsonl", k: int = 5) -> int:
    p = Path(path)
    if not p.exists():
        print(f"missing {p}; create one from data/eval_questions.example.jsonl", file=sys.stderr)
        return 2
    total = hits = 0
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            q = json.loads(line)
            chunks = retrieve(q["question"], k=k)
            ok = _hit(q.get("expected_section", ""), int(q.get("expected_page", 0) or 0), chunks)
            total += 1
            hits += int(ok)
            flag = "HIT" if ok else "MISS"
            print(f"[{flag}] {q['question'][:70]}")
    rate = hits / total if total else 0
    print(f"\nHit@{k} = {hits}/{total} = {rate:.2%}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))

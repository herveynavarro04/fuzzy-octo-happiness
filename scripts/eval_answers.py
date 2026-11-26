#!/usr/bin/env python
"""
Evaluación de respuestas end-to-end.

Lee data/eval_questions.jsonl y por cada pregunta llama a POST /ask (modo single).
Guarda data/eval_results.csv con:

    question, expected_section, expected_page, mode, answer,
    cite_sections, cite_pages, latency_ms, cache_hit, error

Y calcula el resumen según el criterio:

    - correcta       = answer != "No está en el artículo." and found_in_paper
    - cita_correcta  = alguna cita coincide con expected_section (substring) o expected_page
    - rechazo_ok     = expected_* == "none"/"n/a" y la respuesta negó tener evidencia

Uso:
    python scripts/eval_answers.py [--base http://localhost:8000]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import httpx


def _cite_ok(expected_section: str, expected_page: int, citations: list[dict]) -> bool:
    es = (expected_section or "").lower().strip()
    for c in citations:
        if es and es in (c.get("section", "") or "").lower():
            return True
        if expected_page and int(c.get("page", 0)) == expected_page:
            return True
    return False


def main(path: Path, base_url: str, out_csv: Path) -> int:
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    results = []
    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        for q in rows:
            expected_section = q.get("expected_section", "")
            expected_page    = int(q.get("expected_page", 0) or 0)
            is_rejection = expected_section.lower() in {"none", "n/a", ""} and not expected_page

            resp = client.post("/ask", json={"question": q["question"], "mode": "single"})
            if resp.status_code != 200:
                results.append({**q, "error": f"HTTP {resp.status_code}", "answer": "",
                                "cite_sections": "", "cite_pages": "",
                                "latency_ms": 0, "cache_hit": False,
                                "correcta": False, "cita_correcta": False,
                                "rechazo_ok": False})
                continue
            body = resp.json()
            ans = body["answer"]
            citations = ans.get("citations", [])

            correcta = bool(ans.get("found_in_paper")) and ans.get("answer", "").strip() != ""
            cita_ok  = _cite_ok(expected_section, expected_page, citations)
            rechazo_ok = (is_rejection
                          and not ans.get("found_in_paper", True)
                          and "no está en el artículo" in ans.get("answer", "").lower())

            results.append({
                "question": q["question"],
                "expected_section": expected_section,
                "expected_page": expected_page,
                "mode": "single",
                "answer": ans.get("answer", ""),
                "cite_sections": " | ".join(c.get("section", "") for c in citations),
                "cite_pages":    " | ".join(str(c.get("page", 0)) for c in citations),
                "latency_ms": body.get("latency_ms", 0),
                "cache_hit":  body.get("cache_hit", False),
                "correcta":   correcta,
                "cita_correcta": cita_ok,
                "rechazo_ok":   rechazo_ok,
                "error": "",
            })

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        for r in results:
            w.writerow(r)

    # resumen
    n = len(results)
    correctas = sum(1 for r in results if r["correcta"])
    citas_ok  = sum(1 for r in results if r["cita_correcta"])
    rechazos  = sum(1 for r in results if r["rechazo_ok"])
    print(f"\nEvaluación end-to-end sobre {n} preguntas")
    print(f"- correctas (answer con fundamento): {correctas}/{n} = {correctas/n:.2%}")
    print(f"- citas correctas:                   {citas_ok}/{n} = {citas_ok/n:.2%}")
    print(f"- rechazos correctos ('no está'):    {rechazos}/{n}")
    print(f"\nDetalle en: {out_csv}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base",  default="http://localhost:8000")
    p.add_argument("--input", default="data/eval_questions.jsonl")
    p.add_argument("--out",   default="data/eval_results.csv")
    args = p.parse_args()
    path = Path(args.input)
    if not path.exists():
        print(f"missing {path}", file=sys.stderr); sys.exit(2)
    sys.exit(main(path, args.base, Path(args.out)))

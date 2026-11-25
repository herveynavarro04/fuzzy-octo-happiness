import { useState } from "react";
import { ask, type AskResponse } from "../api";
import Citations from "../components/Citations";

export default function Single() {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<AskResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function send() {
    if (!q.trim() || busy) return;
    setBusy(true); setErr(null);
    try {
      setRes(await ask(q, "single"));
    } catch (e: any) { setErr(String(e.message || e)); }
    finally { setBusy(false); }
  }

  return (
    <div className="single">
      <h1>Pregunta única</h1>
      <p className="muted">Sin historial. Las respuestas se cachean 10 min.</p>
      <form className="composer" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <input
          placeholder="Escribe una pregunta…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          disabled={busy}
          autoFocus
        />
        <button type="submit" disabled={busy || !q.trim()}>Preguntar</button>
      </form>
      {err && <div className="error">{err}</div>}
      {res && (
        <div className="answer">
          <div className="answer-meta">
            <span>{res.cache_hit ? "cache HIT" : "cache miss"}</span>
            <span>{res.latency_ms} ms</span>
          </div>
          <div className="bubble">{res.answer.answer}</div>
          <Citations items={res.answer.citations} />
          {!res.answer.found_in_paper && (
            <div className="muted small">Sin evidencia en el artículo.</div>
          )}
        </div>
      )}
    </div>
  );
}

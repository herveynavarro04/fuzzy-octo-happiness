import { useState } from "react";
import { ask, type Answer } from "../api";
import Citations from "../components/Citations";

type Turn = { role: "user" | "assistant"; text: string; answer?: Answer };

export default function Chat() {
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function send() {
    if (!q.trim() || busy) return;
    const question = q;
    setTurns((t) => [...t, { role: "user", text: question }]);
    setQ("");
    setBusy(true);
    setErr(null);
    try {
      const res = await ask(question, "chat", sessionId);
      setSessionId(res.session_id);
      setTurns((t) => [
        ...t,
        { role: "assistant", text: res.answer.answer, answer: res.answer },
      ]);
    } catch (e: any) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="chat">
      <h1>Chat sobre el artículo</h1>
      <p className="muted">Mantiene el historial de la sesión.</p>
      <div className="thread">
        {turns.map((t, i) => (
          <div key={i} className={`turn turn-${t.role}`}>
            <div className="bubble">{t.text}</div>
            {t.answer?.citations && <Citations items={t.answer.citations} />}
          </div>
        ))}
        {busy && <div className="turn turn-assistant"><div className="bubble muted">…</div></div>}
      </div>
      {err && <div className="error">{err}</div>}
      <form
        className="composer"
        onSubmit={(e) => { e.preventDefault(); send(); }}
      >
        <input
          placeholder="Pregunta sobre el artículo…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          disabled={busy}
          autoFocus
        />
        <button type="submit" disabled={busy || !q.trim()}>Enviar</button>
      </form>
    </div>
  );
}

import { useEffect, useState } from "react";
import { adminFetch } from "../api";

type Stats = {
  runs: number;
  input_tokens: number;
  output_tokens: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  avg_retrieval_ms: number;
  cache_hit_rate: number;
  errors: number;
  activity: { hour: string; n: number }[];
};

type Run = {
  id: string;
  mode: string;
  question: string;
  answer: string;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  retrieval_ms: number;
  cache_hit: boolean;
  model: string;
  error: string | null;
  created_at: string;
};

export default function Admin() {
  const [token, setToken] = useState(sessionStorage.getItem("admin_token") || "");
  const [auth, setAuth] = useState(!!sessionStorage.getItem("admin_token"));
  const [stats, setStats] = useState<Stats | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    try {
      const [s, r] = await Promise.all([
        adminFetch("/admin/stats", token),
        adminFetch("/admin/runs?limit=50", token),
      ]);
      setStats(s); setRuns(r); setErr(null);
    } catch (e: any) {
      setErr(String(e.message || e));
      setAuth(false);
      sessionStorage.removeItem("admin_token");
    }
  }

  useEffect(() => { if (auth) load(); /* eslint-disable-next-line */ }, [auth]);

  if (!auth) {
    return (
      <div className="admin-login">
        <h1>Admin</h1>
        <input
          placeholder="X-Admin-Token"
          value={token}
          onChange={(e) => setToken(e.target.value)}
        />
        <button
          onClick={() => { sessionStorage.setItem("admin_token", token); setAuth(true); }}
          disabled={!token.trim()}
        >
          Entrar
        </button>
        {err && <div className="error">{err}</div>}
      </div>
    );
  }

  const maxN = Math.max(1, ...(stats?.activity.map((a) => a.n) || []));

  return (
    <div className="admin">
      <div className="header-row">
        <h1>Admin</h1>
        <button onClick={load} className="ghost">Refrescar</button>
      </div>
      {err && <div className="error">{err}</div>}
      {stats && (
        <>
          <div className="kpis">
            <Kpi label="Corridas" value={stats.runs.toLocaleString()} />
            <Kpi label="Tokens in"  value={stats.input_tokens.toLocaleString()} />
            <Kpi label="Tokens out" value={stats.output_tokens.toLocaleString()} />
            <Kpi label="Latencia avg" value={`${stats.avg_latency_ms} ms`} />
            <Kpi label="Latencia p95" value={`${stats.p95_latency_ms} ms`} />
            <Kpi label="Retrieval avg" value={`${stats.avg_retrieval_ms} ms`} />
            <Kpi label="Cache hit" value={`${(stats.cache_hit_rate * 100).toFixed(1)}%`} />
            <Kpi label="Errores" value={stats.errors.toLocaleString()} />
          </div>
          <div className="activity">
            <div className="section-label">Actividad últimas 24h</div>
            <div className="bars">
              {stats.activity.map((a, i) => (
                <div key={i} className="bar-col" title={`${a.hour}: ${a.n}`}>
                  <div
                    className="bar"
                    style={{ height: `${Math.round((a.n / maxN) * 100)}%` }}
                  />
                </div>
              ))}
              {stats.activity.length === 0 && <div className="muted">sin actividad</div>}
            </div>
          </div>
        </>
      )}
      <div className="section-label">Corridas recientes</div>
      <table className="runs">
        <thead>
          <tr>
            <th>Hora</th><th>Modo</th><th>Pregunta</th><th>Respuesta</th>
            <th>In</th><th>Out</th><th>Latencia</th><th>Cache</th><th>Error</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id} className={r.error ? "err" : ""}>
              <td className="mono">{new Date(r.created_at).toLocaleTimeString()}</td>
              <td>{r.mode}</td>
              <td className="q">{r.question}</td>
              <td className="a">{r.answer}</td>
              <td>{r.input_tokens}</td>
              <td>{r.output_tokens}</td>
              <td>{r.latency_ms} ms</td>
              <td>{r.cache_hit ? "hit" : ""}</td>
              <td className="err-cell">{r.error || ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="kpi">
      <div className="kpi-value">{value}</div>
      <div className="kpi-label">{label}</div>
    </div>
  );
}

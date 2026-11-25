export type Citation = { chunk_id: string; section: string; page: number };
export type Answer = { answer: string; citations: Citation[]; found_in_paper: boolean };
export type AskResponse = {
  answer: Answer;
  session_id: string;
  run_id: string;
  cache_hit: boolean;
  latency_ms: number;
};

export async function ask(
  question: string,
  mode: "chat" | "single",
  sessionId?: string,
): Promise<AskResponse> {
  const r = await fetch("/api/ask", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ question, mode, session_id: sessionId }),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
  return r.json();
}

export async function adminFetch(path: string, token: string): Promise<any> {
  const r = await fetch(`/api${path}`, { headers: { "x-admin-token": token } });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

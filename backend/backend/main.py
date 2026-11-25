"""FastAPI entrypoint. POST /ask, GET /admin/stats, GET /admin/runs."""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from contracts import Answer, AskRequest, AskResponse, Citation
from retrieval.settings import get_settings

from backend import cache, db
from backend.agent import Deps, build_agent

log = logging.getLogger("backend")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.startup()
    await cache.startup()
    app.state.agent = build_agent()
    yield
    await cache.shutdown()
    await db.shutdown()


app = FastAPI(title="RAG agent", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# ------------------------- /ask -------------------------

@app.get("/healthz")
async def healthz():
    return {"ok": True, "fake_models": get_settings().fake_models}


def _client_ip(req: Request) -> str:
    return (req.client.host if req.client else "0.0.0.0") or "0.0.0.0"


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, request: Request) -> AskResponse:
    ip = _client_ip(request)
    if not await cache.rate_limit_ok(ip):
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    s = get_settings()
    model_name = "fake" if s.fake_models else s.llm_model

    # 1) cache (sólo modo single)
    cached_payload = None
    if req.mode == "single":
        cached_payload = await cache.get_cached_answer(req.question)

    t0 = time.perf_counter()
    conv_id = None
    error_text: str | None = None
    retrieved_ids: list[str] = []
    answer_obj: Answer

    try:
        conv_id = await db.ensure_conversation(req.session_id) if req.mode == "chat" else None

        if cached_payload is not None:
            answer_obj = Answer.model_validate(cached_payload["answer"])
            retrieved_ids = cached_payload.get("retrieved_chunk_ids", [])
            cache_hit = True
            input_tokens = 0
            output_tokens = 0
            retrieval_ms = 0
        else:
            cache_hit = False
            deps = Deps(last_chunks=[])
            agent = request.app.state.agent
            t_ret = time.perf_counter()
            result = await asyncio.to_thread(
                agent.run_sync, req.question, deps=deps
            )
            retrieval_ms = int((time.perf_counter() - t_ret) * 1000)
            answer_obj = result.output
            retrieved_ids = [c.id for c in deps.last_chunks]
            try:
                u = result.usage()
                input_tokens  = int(u.request_tokens or 0)
                output_tokens = int(u.response_tokens or 0)
            except Exception:
                input_tokens, output_tokens = 0, 0

        if req.mode == "chat" and conv_id is not None:
            await db.append_message(conv_id, "user", req.question)
            await db.append_message(conv_id, "assistant", answer_obj.answer)
            await cache.push_history(str(conv_id), "user", req.question)
            await cache.push_history(str(conv_id), "assistant", answer_obj.answer)

        if req.mode == "single" and not cache_hit:
            await cache.put_cached_answer(req.question, {
                "answer": answer_obj.model_dump(),
                "retrieved_chunk_ids": retrieved_ids,
            })

    except Exception as e:
        log.exception("ask failed: %s", e)
        error_text = f"{type(e).__name__}: {e}"
        answer_obj = Answer(answer="Error interno.", citations=[], found_in_paper=False)
        input_tokens = output_tokens = retrieval_ms = 0
        cache_hit = False

    latency_ms = int((time.perf_counter() - t0) * 1000)
    run_id = await db.insert_run(
        conversation_id=conv_id,
        mode=req.mode,
        question=req.question,
        answer=answer_obj.answer,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        retrieval_ms=retrieval_ms,
        cache_hit=cache_hit,
        model=model_name,
        retrieved_chunk_ids=retrieved_ids,
        error=error_text,
    )

    if error_text:
        raise HTTPException(status_code=500, detail=error_text)

    return AskResponse(
        answer=answer_obj,
        session_id=str(conv_id) if conv_id else (req.session_id or str(uuid.uuid4())),
        run_id=str(run_id),
        cache_hit=cache_hit,
        latency_ms=latency_ms,
    )


# ------------------------- /admin -------------------------

def require_admin(x_admin_token: str = Header(default="")) -> None:
    expected = os.environ.get("ADMIN_TOKEN", "")
    if not expected or x_admin_token != expected:
        raise HTTPException(status_code=401, detail="invalid admin token")


@app.get("/admin/stats", dependencies=[Depends(require_admin)])
async def admin_stats():
    return await db.stats()


@app.get("/admin/runs", dependencies=[Depends(require_admin)])
async def admin_runs(limit: int = 50):
    return await db.recent_runs(limit=min(max(limit, 1), 500))

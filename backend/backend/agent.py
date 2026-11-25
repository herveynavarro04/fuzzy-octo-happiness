"""
Agente Pydantic AI con:
- herramienta `search_paper` que llama a retrieve();
- output tipado `Answer` con citas;
- system prompt que obliga a citar y a decir "no está en el artículo" si no hay evidencia;
- responde en el idioma de la pregunta;
- modelo real: Ollama vía su API OpenAI-compat (OLLAMA_URL + LLM_MODEL);
- modelo falso: FunctionModel que fuerza la herramienta y arma una respuesta
  con citas reales del resultado de retrieve().
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)

from contracts import Answer, Chunk, Citation
from retrieval.retrieve import retrieve
from retrieval.settings import get_settings

log = logging.getLogger("agent")


@dataclass
class Deps:
    """Lo que el agente guarda por corrida."""
    last_chunks: list[Chunk]


SYSTEM_PROMPT = (
    "Eres un asistente que responde preguntas sobre un artículo científico "
    "concreto. Reglas estrictas:\n"
    "1. SIEMPRE llama primero a la herramienta search_paper con la pregunta.\n"
    "2. Responde ÚNICAMENTE con información presente en los chunks devueltos.\n"
    "3. Cita cada afirmación con la sección y el número de página del chunk.\n"
    "4. Si los chunks no contienen evidencia para la pregunta, responde "
    "   exactamente: 'No está en el artículo.' y deja found_in_paper=false.\n"
    "5. Responde en el mismo idioma en el que está escrita la pregunta.\n"
    "6. No inventes referencias, autores ni números."
)


def _build_search_tool(agent: Agent[Deps, Answer]) -> None:
    @agent.tool
    def search_paper(ctx: RunContext[Deps], query: str, k: int = 5) -> list[dict[str, Any]]:
        """Busca pasajes relevantes del artículo. Devuelve id, text, section, page, kind, score."""
        chunks = retrieve(query, k=k)
        ctx.deps.last_chunks = chunks
        return [c.model_dump() for c in chunks]


# ----------------------------- Fake model -----------------------------

def _fake_model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """
    Primera llamada: pide search_paper(query=última pregunta del usuario).
    Segunda llamada (tras tool-return): emite el Answer final con citas.
    """
    # ¿Ya hay una ToolReturnPart en el historial? -> emitir respuesta.
    tool_returns: list[tuple[str, Any]] = []
    for m in messages:
        if isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, ToolReturnPart):
                    tool_returns.append((p.tool_name, p.content))

    # Última pregunta del usuario (UserPromptPart)
    user_q = ""
    from pydantic_ai.messages import UserPromptPart
    for m in messages:
        if isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, UserPromptPart):
                    user_q = p.content if isinstance(p.content, str) else str(p.content)

    if not tool_returns:
        return ModelResponse(
            parts=[ToolCallPart(
                tool_name="search_paper",
                args={"query": user_q, "k": 5},
                tool_call_id="call-1",
            )]
        )

    # Tenemos chunks -> emitir el output final como tool call al final_result
    chunks_raw = tool_returns[-1][1] or []
    if chunks_raw:
        top = chunks_raw[0]
        section = top.get("section") or "sin sección"
        page = int(top.get("page") or 0)
        snippet = (top.get("text") or "").strip().replace("\n", " ")[:220]
        answer_text = (
            f"[FAKE_MODELS=true] Según {section} (p. {page}): {snippet}…"
        )
        citations = [
            {"chunk_id": c["id"], "section": c.get("section", ""), "page": int(c.get("page", 0))}
            for c in chunks_raw[:3]
        ]
        found = True
    else:
        answer_text = "No está en el artículo."
        citations = []
        found = False

    return ModelResponse(
        parts=[ToolCallPart(
            tool_name="final_result",
            args={
                "answer": answer_text,
                "citations": citations,
                "found_in_paper": found,
            },
            tool_call_id="call-2",
        )]
    )


# ----------------------------- Model factory -----------------------------

def _build_model():
    s = get_settings()
    if s.fake_models:
        return FunctionModel(_fake_model_fn)
    # Ollama expone /v1 compatible con OpenAI
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.openai import OpenAIProvider
    provider = OpenAIProvider(
        base_url=s.ollama_url.rstrip("/") + "/v1",
        api_key="ollama",
    )
    return OpenAIModel(s.llm_model, provider=provider)


def build_agent() -> Agent[Deps, Answer]:
    reasoning_effort = os.getenv("OLLAMA_REASONING_EFFORT")
    model_settings = (
        {"extra_body": {"reasoning_effort": reasoning_effort}}
        if reasoning_effort and not get_settings().fake_models
        else None
    )
    agent = Agent[Deps, Answer](
        _build_model(),
        deps_type=Deps,
        output_type=Answer,
        system_prompt=SYSTEM_PROMPT,
        model_settings=model_settings,
    )
    _build_search_tool(agent)
    return agent


__all__ = ["build_agent", "Deps", "SYSTEM_PROMPT"]

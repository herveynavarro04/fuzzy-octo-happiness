from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

ChunkKind = Literal["text", "table", "figure"]
Mode = Literal["chat", "single"]


class Chunk(BaseModel):
    id: str
    text: str
    section: str = ""
    page: int = 0
    kind: ChunkKind = "text"
    score: float = 0.0


class Citation(BaseModel):
    chunk_id: str
    section: str
    page: int


class Answer(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    found_in_paper: bool = True


class AskRequest(BaseModel):
    question: str
    mode: Mode = "single"
    session_id: Optional[str] = None


class AskResponse(BaseModel):
    answer: Answer
    session_id: str
    run_id: str
    cache_hit: bool = False
    latency_ms: int = 0


class Run(BaseModel):
    id: UUID
    conversation_id: Optional[UUID] = None
    mode: Mode
    question: str
    answer: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    retrieval_ms: int = 0
    cache_hit: bool = False
    model: str = ""
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    created_at: datetime

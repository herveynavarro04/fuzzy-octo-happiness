-- Esquema para el agente RAG. Carga conversations/messages/runs.
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS conversations (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_messages_conv_time
    ON messages (conversation_id, created_at);

CREATE TABLE IF NOT EXISTS runs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id      UUID REFERENCES conversations(id) ON DELETE SET NULL,
    mode                 TEXT NOT NULL CHECK (mode IN ('chat', 'single')),
    question             TEXT NOT NULL,
    answer               TEXT NOT NULL DEFAULT '',
    input_tokens         INTEGER NOT NULL DEFAULT 0,
    output_tokens        INTEGER NOT NULL DEFAULT 0,
    latency_ms           INTEGER NOT NULL DEFAULT 0,
    retrieval_ms         INTEGER NOT NULL DEFAULT 0,
    cache_hit            BOOLEAN NOT NULL DEFAULT false,
    model                TEXT NOT NULL DEFAULT '',
    retrieved_chunk_ids  TEXT[] NOT NULL DEFAULT '{}',
    error                TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_mode       ON runs (mode);
CREATE INDEX IF NOT EXISTS idx_runs_error      ON runs ((error IS NOT NULL));

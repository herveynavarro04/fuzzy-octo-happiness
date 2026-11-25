# Agente RAG sobre un survey Q1

Agente que responde preguntas sobre el survey
*"From language to action: a review of large language models as autonomous agents and tool users"*
(PDF en `resources/article.pdf`).

- UI con dos modos: chat con historial (`/`) y pregunta única sin historial (`/single`).
- Panel `/admin` con KPIs: tokens entrada/salida, latencia promedio y p95, tasa de cache hit, errores, actividad por hora y corridas recientes.
- Hoy (Hervey) todo corre con **`FAKE_MODELS=true`** (sin vLLM ni Hugging Face).
- Mañana (Miguel) sólo cambia variables de `.env` para encender los modelos reales.

Stack: FastAPI, Pydantic AI, PostgreSQL, Redis, OpenSearch, React+Vite+TS, Docling, vLLM, Ollama, Hugging Face, Docker, ngrok.

## Levantar con modelos falsos

```bash
cp .env.example .env            # FAKE_MODELS=true por defecto
make smoke                      # levanta stack, ingesta fake, pregunta, verifica /admin
```

Luego abres:

- http://localhost:5173/        — chat
- http://localhost:5173/single  — pregunta única
- http://localhost:5173/admin   — token = `ADMIN_TOKEN` de `.env` (por defecto `changeme-admin-token`)

Para la UI:

```bash
make up                         # añade el contenedor frontend
```

Apagar todo:

```bash
make down
```

## Qué levanta cada perfil del compose

| Perfil   | Servicios                                  | Dónde corre        |
| -------- | ------------------------------------------ | ------------------ |
| default  | postgres, redis, opensearch, api, frontend | Mac de Hervey (OK) |
| models   | vllm-embed, vllm-rerank                    | Mac de Miguel      |
| ingest   | vllm-vlm (Qwen2.5-VL-7B)                   | Mac de Miguel/Colab |
| tunnel   | ngrok                                      | Mac de Miguel      |

Ollama corre **nativo** en el host (no en Docker) y los contenedores lo llaman por `host.docker.internal:11434`.

## Ingesta por etapas

```bash
# dentro del contenedor api (o localmente activando el venv)
python -m retrieval.ingest chunks        # PDF -> data/chunks.jsonl + data/figures/
python -m retrieval.ingest figures       # describe figuras con Qwen2.5-VL (perfil ingest)
python -m retrieval.ingest embeddings    # calcula embeddings (reales o falsos)
python -m retrieval.ingest load          # crea índice y bulk-load a OpenSearch
python -m retrieval.ingest all           # las 4 en orden
```

Con `FAKE_MODELS=true` no hace llamadas de red: embeddings deterministas por hash y descripciones de figuras falsas.

## Evaluación

```bash
cp data/eval_questions.example.jsonl data/eval_questions.jsonl   # escribe 25-30 preguntas
make eval
```

Mide `Hit@5`: considera hit si algún chunk devuelto por `retrieve()` coincide con la sección esperada (substring) o con la página esperada.

## Estructura

```
contracts/   # modelos Pydantic compartidos (Chunk, Answer, Run, AskRequest/Response)
retrieval/   # Docling, clientes HTTP, OpenSearch, retrieve híbrido
backend/     # FastAPI + agente Pydantic AI + persistencia
frontend/    # React + Vite + TypeScript
infra/       # docker-compose.yml + init.sql
scripts/     # download_models.py, seed_runs.py, eval.py
data/        # chunks.jsonl, figures/, eval_questions.jsonl (gitignored)
resources/   # artículo (PDF) y documento de división (no modificar)
```

## Traspaso

Miguel: ver [HANDOFF.md](./HANDOFF.md).

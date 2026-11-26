# Agente RAG sobre un survey Q1

Agente que responde preguntas sobre el survey
*"From language to action: a review of large language models as autonomous agents and tool users"*
(PDF en `resources/article.pdf`).

- UI con dos modos: chat con historial (`/`) y pregunta única sin historial (`/single`).
- Panel `/admin` con KPIs: tokens entrada/salida, latencia promedio y p95, tasa de cache hit, errores, actividad por hora y corridas recientes.

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
docker compose -f infra/docker-compose.yml --env-file .env cp \
  data/eval_questions.jsonl api:/app/data/eval_questions.jsonl
docker compose -f infra/docker-compose.yml --env-file .env exec -T api \
  python /app/scripts/eval.py /app/data/eval_questions.jsonl
```

Mide `Hit@5`: considera hit si algún chunk devuelto por `retrieve()` coincide con la sección esperada (substring) o con la página esperada.

### Prueba local en la Mac de Miguel (25 de noviembre de 2026)

- **Hit@5 de 24/28 (85.71 %)** con el índice final. Contiene 446 fragmentos de texto y tablas y las siete figuras numeradas del artículo descritas con Qwen2.5-VL 7B en Ollama.
- La configuración local usó embeddings Nemotron de 1024 dimensiones servidos por llama.cpp, búsqueda híbrida en OpenSearch, reranker desactivado y Nemotron 3 Nano 4B en Ollama con una ventana de 16 384 tokens. La pregunta de demostración sobre LOMAR devolvió citas de la sección 6.1.1 y la figura 4, ambas en la página 19.
- Durante el ensayo, macOS reportó **20 GB utilizados** en el equipo. Docker reportó **1.08 GiB** sumados entre los cinco contenedores y Ollama reportó **3.3 GB** para el modelo de chat. La cifra de macOS incluye el resto de procesos del equipo.
- La demo se ejecutó en `http://localhost:5173/`. La pregunta de LOMAR tardó 78 segundos. El chat respondió «No está en el artículo.» a una pregunta sin evidencia y el panel de administración exigió el token. La validación de vLLM y su reranker quedó pendiente.

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

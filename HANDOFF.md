# Traspaso para Miguel (25 de noviembre)

Hervey dejó todo el código funcionando con `FAKE_MODELS=true`. Este documento
tiene los comandos exactos, en orden, para encender los modelos reales en tu
Mac (24 GB) y correr la evaluación y la demo.

Si algo de MI código falla, llámame y lo arreglo yo (no toques el código tú).
Si falla algo en vLLM / Ollama / tu sistema, eso es tu parte.

---

## 0. Antes de empezar

```bash
git pull
cp .env.example .env
make smoke          # debe pasar con FAKE_MODELS=true igual que en mi Mac
```

Si `make smoke` falla en tu Mac con modelos falsos: me llamas, es culpa mía.

---

## 1. Descargar los tres modelos

Los contenedores de vLLM comparten el volumen `hfcache` (ver compose). Para
poblarlo:

```bash
# si algún modelo lo pide:
export HUGGING_FACE_HUB_TOKEN=hf_xxx

# descarga a /models dentro del contenedor (volumen hfcache compartido)
docker compose -f infra/docker-compose.yml run --rm --entrypoint "" \
    vllm-embed  python /app/scripts/download_models.py embed
docker compose -f infra/docker-compose.yml run --rm --entrypoint "" \
    vllm-rerank python /app/scripts/download_models.py rerank
docker compose -f infra/docker-compose.yml run --rm --entrypoint "" \
    vllm-vlm    python /app/scripts/download_models.py vlm
```

Alternativa: en el host con `export HF_HOME=...` y `python scripts/download_models.py`.

Tamaños aproximados (según model cards):

| Modelo                                   | Tamaño  |
| ---------------------------------------- | ------- |
| nvidia/Nemotron-3-Embed-1B-BF16          | ~2.3 GB |
| nvidia/llama-nemotron-rerank-1b-v2       | ~2.5 GB |
| Qwen/Qwen2.5-VL-7B-Instruct              | ~15 GB  |

---

## 2. Levantar vLLM (embeddings + reranker)

> ⚠️ **NO VERIFICADO en macOS sin GPU NVIDIA.** Yo no lo probé. Si falla,
> guarda el `docker compose logs` y consulta al profe (no inventes flags).

```bash
docker compose -f infra/docker-compose.yml --profile models up -d vllm-embed vllm-rerank
docker compose -f infra/docker-compose.yml logs -f vllm-embed  vllm-rerank
```

Flags que ya están en el compose y que confirman las model cards:

- `vllm-embed`: `--task embed --trust-remote-code` y versión de imagen `vllm/vllm-openai:v0.11.0` (versión pinned porque la model card del embed pide una versión reciente con soporte limpio a `/v1/embeddings`). TODO: confirmar que esta versión es la que tu model card lista.
- `vllm-rerank`: `--task score --trust-remote-code`. La plantilla de scoring la aplica vLLM al servir en `--task score` (el cliente `RerankClient` manda `{"text_1": query, "text_2": docs}` a `/v1/score`). TODO: confirmar que vLLM 0.11.0 expone `/v1/score` para este modelo.
- `vllm-vlm`: `--trust-remote-code --max-model-len 8192`.

Smoke test de los dos servicios:

```bash
curl -s http://localhost:8001/v1/models | jq .
curl -s http://localhost:8002/v1/models | jq .
curl -s http://localhost:8001/v1/embeddings \
  -H 'content-type: application/json' \
  -d '{"model":"nvidia/Nemotron-3-Embed-1B-BF16","input":["query: hello"]}' | jq '.data[0].embedding | length'
```

---

## 3. Levantar Ollama nativo

**Fuera de Docker**, con la GPU de Apple:

```bash
brew install ollama
brew services start ollama
ollama pull nemotron-3-nano:4b
ollama run nemotron-3-nano:4b "hola"   # prueba
```

Los contenedores ya lo llaman por `host.docker.internal:11434` (compose tiene `extra_hosts`).

---

## 4. Ingesta real

Con los 3 servicios de vLLM arriba y Ollama corriendo, con `FAKE_MODELS=true` todavía:

```bash
# chunks + figuras extraídas con Docling
make up              # postgres, redis, opensearch, api, frontend
docker compose -f infra/docker-compose.yml exec api python -m retrieval.ingest chunks

# figuras con Qwen2.5-VL (perfil ingest)
docker compose -f infra/docker-compose.yml --profile ingest up -d vllm-vlm
docker compose -f infra/docker-compose.yml exec api python -m retrieval.ingest figures
docker compose -f infra/docker-compose.yml --profile ingest down

# embeddings reales (requiere FAKE_MODELS=false y vllm-embed arriba)
sed -i '' 's/^FAKE_MODELS=true/FAKE_MODELS=false/' .env
docker compose -f infra/docker-compose.yml restart api
docker compose -f infra/docker-compose.yml exec api python -m retrieval.ingest embeddings
docker compose -f infra/docker-compose.yml exec api python -m retrieval.ingest load
```

**Si Qwen2.5-VL no cabe en tus 24 GB:** sube el notebook `scripts/figures_colab.ipynb` (TODO Hervey: escribirlo si lo necesitas) a Colab, descarga figuras locales y corre allí la etapa `figures`, luego copia el `chunks.jsonl` actualizado de vuelta antes de `embeddings`.

---

## 5. Pasar a modelos reales (sólo variables)

En `.env`:

```diff
-FAKE_MODELS=true
+FAKE_MODELS=false
```

Reinicia `api`:

```bash
docker compose -f infra/docker-compose.yml restart api
```

Smoke test:

```bash
curl -s -X POST http://localhost:8000/ask \
  -H 'content-type: application/json' \
  -d '{"question":"¿De qué trata el artículo?","mode":"single"}' | jq .
```

Debe citar sección y página reales.

---

## 6. Evaluación (25–30 preguntas)

Escribe las preguntas leyendo el PDF:

```bash
cp data/eval_questions.example.jsonl data/eval_questions.jsonl
# edita y añade 25-30 líneas con {question, expected_section, expected_page}
make eval
```

Anota el `Hit@5` en el `README.md`.

---

## 7. ngrok y RAM

```bash
export NGROK_AUTHTOKEN=tu_token
docker compose -f infra/docker-compose.yml --profile tunnel up -d ngrok
docker compose -f infra/docker-compose.yml logs ngrok | grep 'started tunnel'
# abre http://localhost:4040 para ver la URL pública
```

Medir RAM total durante la demo:

```bash
docker stats --no-stream --format "table {{.Container}}\t{{.MemUsage}}"
```

Anota el total en el README antes de la demo.

---

## 8. Variables de `.env` que puedes tener que cambiar

| Variable        | Para qué                                                         |
| --------------- | ---------------------------------------------------------------- |
| `FAKE_MODELS`   | `true` → modo falso, `false` → modelos reales                    |
| `EMBED_URL`     | si decides exponer vLLM en otro puerto                           |
| `EMBED_DIM`     | **NO lo cambies** sin reindexar (el índice fija dim=1024)        |
| `RERANK_URL`    | ídem                                                             |
| `USE_RERANKER`  | ponlo en `false` si el reranker no corre                         |
| `VLM_URL`       | ídem                                                             |
| `OLLAMA_URL`    | si corres Ollama en otro puerto                                  |
| `LLM_MODEL`     | si decides probar `nemotron-3-nano:9b` o similar                 |
| `ADMIN_TOKEN`   | cámbialo antes de abrir el túnel                                 |
| `NGROK_AUTHTOKEN` | el tuyo                                                        |

Contratos (**no cambiar sin avisarme**): `Chunk`, `Answer`, tabla `runs`.

---

## 9. Qué está hecho (Hervey) y qué no

### Hecho

- Monorepo con `contracts/`, `retrieval/`, `backend/`, `frontend/`, `infra/`, `scripts/`, `data/`.
- Contratos Pydantic y `.env.example`.
- Compose con 4 perfiles (default, models, ingest, tunnel) y 9 servicios.
- `scripts/download_models.py` listo (no corrido).
- Ingesta Docling por etapas, con fallback a chunker falso si Docling se queda sin RAM.
- Clientes HTTP para embed, rerank y VLM (OpenAI-compat) con prefijos `query:`/`passage:` y recorte a `EMBED_DIM` + renormalización.
- OpenSearch: índice BM25 + knn_vector (cosine), bulk load, `retrieve()` híbrido con RRF y rerank opcional detrás de `USE_RERANKER`; cache en Redis.
- Agente Pydantic AI 0.4.11 con `search_paper`, `output_type=Answer`, system prompt que obliga a citar y responder "No está en el artículo." sin evidencia.
- `FunctionModel` falso que cita secciones y páginas reales de los chunks devueltos.
- FastAPI con `/ask` (modos chat y single), `/admin/stats`, `/admin/runs` (header `X-Admin-Token`), rate limit, caché single y historial chat en Redis, un registro en `runs` por cada pregunta (incluidas las que fallan).
- Agregaciones con `percentile_cont` para p95.
- Frontend React+Vite+TS con `/`, `/single`, `/admin` (KPIs + gráfica de actividad + tabla de corridas); `tsc -b` limpio, `vite build` pasa.
- `make smoke`, `scripts/seed_runs.py`, `scripts/eval.py`, `data/eval_questions.example.jsonl` con 3 preguntas reales.

### No hecho / sin verificar

- **vLLM en macOS sin GPU NVIDIA: NO VERIFICADO.** El compose tiene los comandos, pero yo no los corrí. Ésta es tu primera parada mañana.
- Versión exacta de la imagen vLLM: pinned a `v0.11.0`. Si la model card de embed/rerank pide otra, cambias el tag y listo.
- Endpoint real `/v1/score` del reranker en esa versión de vLLM: a confirmar.
- Notebook de Colab para Qwen-VL: TODO si no cabe en tu Mac.
- Ingesta real sobre el PDF: queda pendiente, es parte de tu día (yo probé Docling con el chunker fallback si no cabía).
- 25–30 preguntas para la evaluación: las escribes tú leyendo el paper.
- Medir y anotar RAM total y Hit@5: parte de tu checklist.

---

## 10. Problemas conocidos

- `opentelemetry-api` necesita versión `1.28.0` (o compatible) para que `pydantic-ai 0.4.11` importe `opentelemetry._events`. Fijado en `backend/pyproject.toml`.
- OpenSearch con heap de 512 MB puede tardar ~20 s en levantar la primera vez.
- El agente falso **cita chunks reales** del retrieval; eso valida el contrato, pero el texto de la respuesta es un prefijo + snippet, no una redacción natural. Eso cambia al pasar a Ollama.

---

## 11. Para el README — PENDIENTEs que tienes que llenar

El `README.md` tiene 10 marcadores `PENDIENTE` que debes completar para que
el profe califique todos los criterios de la rúbrica. Lista con comando
exacto y dónde pegar el resultado:

### A. Evidencia de cuartil Q1 (sección 2)

- **Qué**: captura de SJR o JCR mostrando que *Artificial Intelligence Review*
  es Q1 en "Artificial Intelligence".
- **Cómo**: abre https://www.scimagojr.com/journalsearch.php?q=24059&tip=sid
  y screenshot del año 2024 o 2025.
- **Dónde guardar**: `docs/evidencia_q1.png`.
- **Dónde referenciar en README**: sección 2, reemplaza el bloque
  `> PENDIENTE (Hervey): ...` por `![Evidencia Q1](docs/evidencia_q1.png)`.

### B. Chip y RAM total (sección 4)

- **Comando**:
  ```bash
  system_profiler SPHardwareDataType | grep -E "Chip|Memory"
  # con todo arriba:
  docker stats --no-stream --format "table {{.Container}}\t{{.MemUsage}}"
  ps -axm -o rss,command | grep ollama | awk '{sum+=$1} END {print "ollama RSS MB:", sum/1024}'
  ```
- **Pegar** el chip y la suma en la tabla de la sección 4.

### C. Un chunk de figura real (sección 5)

- **Comando** (con `FAKE_MODELS=false` y perfil `ingest` arriba):
  ```bash
  docker compose -f infra/docker-compose.yml exec api \
      python -m retrieval.ingest figures
  docker compose -f infra/docker-compose.yml exec api \
      grep '"kind":"figure"' data/chunks.jsonl | head -1 | python -m json.tool
  ```
- **Pegar** el JSON como cuarto ejemplo en el bloque de chunks de la sección 5.

> **Nota de estado (25-nov):** los puntos F (bench_cache) y G (panel admin
> KPIs) ya tienen números reales en el README y archivos de evidencia en
> `docs/admin_*.json`; el punto H (healthchecks) ya está en el compose;
> el punto A (captura Q1) lo hace Hervey a mano.
> Lo que sigue aquí abajo es lo que **requiere modelos reales** mañana.

### D. Tabla Hit@5 / MRR@5 (sección 6)

- **Comando** (con modelos reales):
  ```bash
  docker compose -f infra/docker-compose.yml exec api \
      python /app/scripts/eval_retrieval.py -k 5
  ```
- **Pegar** la tabla markdown que imprime, reemplazando la tabla con
  `PENDIENTE | PENDIENTE` de la sección 6.

### E. Dataset y resultados end-to-end (sección 8)

- **Escribir** ≥ 15 preguntas (idealmente 25–30) en
  `data/eval_questions.jsonl`. Cubrir:
  - 10 preguntas de texto en secciones distintas,
  - 3 sobre figuras,
  - 3 sobre tablas,
  - 3 que el artículo no responde (pon `expected_section: "none"`,
    `expected_page: 0`).
- **Comando**:
  ```bash
  docker compose -f infra/docker-compose.yml exec api \
      python /app/scripts/eval_answers.py --base http://api:8000
  ```
- **Pegar** las primeras ~15 filas de `data/eval_results.csv` como tabla
  markdown en la sección 8, y las 3 líneas de resumen debajo.

### F. Latencia con / sin caché (sección 9)

- **Comando**:
  ```bash
  docker compose -f infra/docker-compose.yml exec api \
      python /app/scripts/bench_cache.py --n 10 --redis redis://redis:6379/0
  ```
- **Pegar** la tabla markdown en la sección 9.

### G. Capturas del panel `/admin` (sección 10)

- **Comando** (datos simulados primero):
  ```bash
  docker compose -f infra/docker-compose.yml exec api \
      python /app/scripts/seed_runs.py 50
  open http://localhost:5173/admin   # token = ADMIN_TOKEN de .env
  ```
- **Guardar** la captura como `docs/admin.png` y referenciar en la sección 10.

### H. Healthchecks en api y frontend (sección 13)

- **Qué falta**: healthcheck HTTP para `api` (curl a `/healthz`) y
  `frontend` (curl a `/`).
- **Cómo**: añadir a `infra/docker-compose.yml` bajo cada servicio:
  ```yaml
      healthcheck:
        test: ["CMD-SHELL", "curl -sf http://localhost:8000/healthz || exit 1"]
        interval: 10s
        timeout: 3s
        retries: 10
  ```
- **Dónde referenciar**: quita el TODO de la sección 13 cuando lo hagas.

### I. Evidencia del rerank on/off (sección 14)

- **Comando** (dos corridas):
  ```bash
  # con rerank
  sed -i '' 's/^USE_RERANKER=.*/USE_RERANKER=true/'  .env
  docker compose -f infra/docker-compose.yml restart api
  docker compose -f infra/docker-compose.yml exec api \
      python /app/scripts/eval_retrieval.py -k 5 | tee /tmp/with_rr.md
  # sin rerank
  sed -i '' 's/^USE_RERANKER=.*/USE_RERANKER=false/' .env
  docker compose -f infra/docker-compose.yml restart api
  docker compose -f infra/docker-compose.yml exec api \
      python /app/scripts/eval_retrieval.py -k 5 | tee /tmp/no_rr.md
  ```
- **Pegar** ambos resultados en la sección 14 como "con rerank" vs
  "sin rerank".

### J. Figura real en la tabla de la sección 14

- Ya queda cubierto por el paso C — basta con que un chunk tipo `figure`
  tenga descripción no-vacía y se cite en alguna respuesta de la evaluación.


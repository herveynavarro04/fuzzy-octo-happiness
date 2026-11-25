.PHONY: smoke up down logs ingest seed eval build-frontend

ENV_FILE ?= .env
COMPOSE = docker compose -f infra/docker-compose.yml --env-file $(ENV_FILE)

up:
	$(COMPOSE) up -d --build postgres redis opensearch api frontend

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

# Corre la ingesta dentro del contenedor api (FAKE_MODELS se lee del .env).
ingest:
	$(COMPOSE) exec -T api python -m retrieval.ingest chunks
	$(COMPOSE) exec -T api python -m retrieval.ingest embeddings
	$(COMPOSE) exec -T api python -m retrieval.ingest load

seed:
	$(COMPOSE) exec -T api python /app/scripts/seed_runs.py 30 || true

eval:
	$(COMPOSE) exec -T api python /app/scripts/eval.py data/eval_questions.example.jsonl

# ---------------- smoke ----------------
# 1. (re)crea .env desde .env.example si falta
# 2. levanta postgres + redis + opensearch + api (sin frontend para ir más rápido)
# 3. espera health
# 4. corre ingesta FAKE (chunks + embeddings + load)
# 5. pregunta una por modo
# 6. verifica runs >= 2 y /admin/stats OK
smoke:
	@test -f $(ENV_FILE) || cp .env.example $(ENV_FILE)
	@grep -q '^FAKE_MODELS=true' $(ENV_FILE) || (echo "ERROR: $(ENV_FILE) must have FAKE_MODELS=true for smoke" && exit 1)
	$(COMPOSE) up -d --build postgres redis opensearch api
	@echo "waiting for /healthz..."
	@for i in $$(seq 1 60); do \
	  curl -sf http://localhost:8000/healthz >/dev/null && echo "api up" && break; \
	  sleep 2; \
	done
	@curl -sf http://localhost:8000/healthz | grep -q '"ok":true' || (echo "api did not come up" && $(COMPOSE) logs api | tail -40 && exit 1)
	$(COMPOSE) exec -T api python -m retrieval.ingest chunks
	$(COMPOSE) exec -T api python -m retrieval.ingest embeddings
	$(COMPOSE) exec -T api python -m retrieval.ingest load
	@echo "--- single mode question ---"
	@curl -sf -X POST http://localhost:8000/ask \
	  -H 'content-type: application/json' \
	  -d '{"question":"¿De qué trata el artículo?","mode":"single"}' | tee /tmp/ans_single.json | head -c 400 ; echo
	@echo "--- chat mode question ---"
	@curl -sf -X POST http://localhost:8000/ask \
	  -H 'content-type: application/json' \
	  -d '{"question":"¿Qué herramientas usan los agentes?","mode":"chat"}' | tee /tmp/ans_chat.json | head -c 400 ; echo
	@echo "--- /admin/stats ---"
	@TOK=$$(grep '^ADMIN_TOKEN=' $(ENV_FILE) | cut -d= -f2); \
	  curl -sf -H "x-admin-token: $$TOK" http://localhost:8000/admin/stats | tee /tmp/stats.json | head -c 400 ; echo
	@python -c "import json,sys; s=json.load(open('/tmp/stats.json')); assert s['runs']>=2, s; print('SMOKE OK runs=', s['runs'])"

build-frontend:
	cd frontend && npm install && npm run build

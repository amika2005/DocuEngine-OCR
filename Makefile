.PHONY: dev dev-infra api worker frontend test test-backend test-frontend lint eval build-bundle clean

# --- Development ---

dev-infra:
	docker compose -f docker/docker-compose.dev.yml up -d postgres redis

dev: dev-infra
	@echo "Infra up. Run 'make api', 'make worker' and 'make frontend' in separate terminals."

api:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

worker:
	cd backend && uv run celery -A app.tasks.celery_app worker -Q cpu,ocr_gpu -c 1 --loglevel=info

frontend:
	cd frontend && npm run dev

# --- Tests ---

test: test-backend test-frontend

test-backend:
	cd backend && uv run pytest -q

test-frontend:
	cd frontend && npm run build

lint:
	cd backend && uv run ruff check app tests
	cd frontend && npm run typecheck

# --- Evaluation against the golden set ---

eval:
	cd backend && uv run python -m app.ocr.eval_golden ../scripts/golden_set

# --- Offline bundle for client installs ---

build-bundle:
	bash docker/installer/bundle.sh

clean:
	rm -rf backend/.pytest_cache backend/.ruff_cache frontend/dist watcher-app/dist

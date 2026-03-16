.PHONY: up down backend frontend lint test index

up:
	docker compose -f docker/docker-compose.yml up -d

down:
	docker compose -f docker/docker-compose.yml down

backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

lint:
	cd backend && uv run black --check . && uv run isort --check . && uv run pylint --fail-under=9.5 app/

format:
	cd backend && uv run black . && uv run isort .

test:
	cd backend && uv run pytest --cov=app --cov-fail-under=80

typecheck:
	cd backend && uv run mypy app/ --strict

index:
	cd backend && uv run python -m app.cli.index $(REPO)

.PHONY: up down backend frontend lint test index create-cypher-model validate-training export-training eval eval-report

up:
	docker compose -f docker/docker-compose.yml up -d

down:
	docker compose -f docker/docker-compose.yml down

backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8111

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

create-cypher-model:
	ollama create cypher-specialist -f backend/models/cypher-specialist.Modelfile

validate-training:
	cd backend && uv run python -m scripts.validate_training_data

export-training:
	cd backend && uv run python -m scripts.export_for_finetuning --format $(or $(FORMAT),alpaca)

eval:
	python -m eval.sandbox.harness --tasks eval/tasks/sample_tasks.jsonl --repo test_repos/sample_app --model $(or $(MODEL),mistral:latest)

eval-report:
	python -m eval.scripts.report $(RESULTS)

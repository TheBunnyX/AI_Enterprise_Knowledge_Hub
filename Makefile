up:
	docker compose up -d --build
down:
	docker compose down
logs:
	docker compose logs -f
migrate:
	docker compose exec api alembic upgrade head
seed:
	docker compose exec api python -c "from hub.seed import seed; seed()"
test:
	cd apps/api && ../../.venv/bin/python -m pytest -q  # needs: docker compose -f compose.yaml -f compose.dev.yaml up -d postgres
lint:
	cd apps/web && npm run typecheck
eval:
	cd apps/api && ../../.venv/bin/python -m eval.run --min-hit 0.9
dev:
	docker compose -f compose.yaml -f compose.dev.yaml up -d --build
	docker compose -f compose.yaml -f compose.dev.yaml watch

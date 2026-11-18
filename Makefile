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
eval-answers:  # Ragas answer quality (calls the judge LLM, see eval/answers.py); add ARGS=--langfuse to record the scores in Langfuse
	cd apps/api && ../../.venv/bin/python -m eval.answers $(ARGS)
eval-deepeval:  # DeepEval answer quality + citation accuracy (calls the judge LLM, see eval/deepeval_run.py); needs .venv-eval; ARGS="--min-faithfulness 0.8 --min-citation 0.7" makes it a gate
	cd apps/api && ../../.venv/bin/python -m eval.answers --dump /tmp/hub-eval-answers.json && ../../.venv-eval/bin/python -m eval.deepeval_run /tmp/hub-eval-answers.json $(ARGS)
dev:
	docker compose -f compose.yaml -f compose.dev.yaml up -d --build
	docker compose -f compose.yaml -f compose.dev.yaml watch
e2e:  # browser tests of the search page; needs the stack up and: npm i --no-save playwright && npx playwright install chromium
	cd apps/web && node e2e/search.e2e.mjs

.PHONY: install dev run test lint clean docker-up docker-down

install:
	pip install -e ".[dev]"

dev:
	python -m red_eyes.cli config/settings.yaml

run:
	python -m red_eyes.cli

test:
	pytest tests/ -v

lint:
	ruff check src/
	ruff format --check src/

lint-fix:
	ruff check src/ --fix
	ruff format src/

clean:
	rm -rf data/events/* data/keyframes/*
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

ollama-pull:
	ollama pull qwen2-vl:2b

setup: install ollama-pull
	@echo "Setup complete. Configure .env and config/settings.yaml before running."

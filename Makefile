.PHONY: sync fingerprint dos cli lint format test start-dev stop-dev restart-dev logs-dev help

sync:
	uv sync

fingerprint:
	uv run cw-fingerprint

dos:
	uv run cw-dos

cli:
	uv run carelesswhisper

lint:
	uv run flake8 carelesswhisper
	uv run mypy carelesswhisper

format:
	uv run black carelesswhisper

test:
	uv run pytest

start-dev:
	docker-compose -f .deploy/docker/docker-compose.yml up -d

stop-dev:
	docker-compose -f .deploy/docker/docker-compose.yml down

restart-dev: stop-dev start-dev

logs-dev:
	docker-compose -f .deploy/docker/docker-compose.yml logs -f

help:
	@echo "Available targets:"
	@echo "  make sync         - Install dependencies with uv"
	@echo "  make cli          - Run the interactive CLI tool"
	@echo "  make fingerprint  - Run the fingerprint tool"
	@echo "  make dos          - Run the DoS tool"
	@echo "  make lint         - Run flake8 and mypy"
	@echo "  make format       - Format code with black"
	@echo "  make test         - Run the test suite"
	@echo "  make start-dev    - Start Docker development environment"
	@echo "  make stop-dev     - Stop Docker development environment"
	@echo "  make restart-dev  - Restart Docker development environment"
	@echo "  make logs-dev     - View Docker development logs"

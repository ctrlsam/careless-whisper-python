.PHONY: start-dev stop-dev restart-dev logs-dev

start-dev:
	docker-compose -f .deploy/docker/docker-compose.yml up -d

stop-dev:
	docker-compose -f .deploy/docker/docker-compose.yml down

restart-dev: stop-dev start-dev

logs-dev:
	docker-compose -f .deploy/docker/docker-compose.yml logs -f

help:
	@echo "Available targets:"
	@echo "  make start-dev    - Start Docker development environment"
	@echo "  make stop-dev     - Stop Docker development environment"
	@echo "  make restart-dev  - Restart Docker development environment"
	@echo "  make logs-dev     - View Docker development logs"

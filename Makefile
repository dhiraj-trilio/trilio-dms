.PHONY: help install install-dev test test-unit test-integration clean lint format build docker-build docker-up docker-down

help:
	@echo "Trilio DMS - Available commands:"
	@echo "  install          - Install package"
	@echo "  install-dev      - Install package with development dependencies"
	@echo "  test             - Run all tests"
	@echo "  test-unit        - Run unit tests only"
	@echo "  test-integration - Run integration tests"
	@echo "  clean            - Clean build artifacts"
	@echo "  lint             - Run linting"
	@echo "  format           - Format code with black"
	@echo "  build            - Build distribution packages"
	@echo "  docker-build     - Build Docker images"
	@echo "  docker-up        - Start services with docker-compose"
	@echo "  docker-down      - Stop services"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

test:
	pytest tests/

test-unit:
	pytest tests/ -m "not integration"

test-integration:
	RUN_INTEGRATION_TESTS=1 pytest tests/ -m integration

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.pyo' -delete

lint:
	flake8 trilio_dms tests examples
	mypy trilio_dms

format:
	black trilio_dms tests examples

build: clean
	python setup.py sdist bdist_wheel

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

# Database commands
db-create:
	mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS trilio_dms;"
	mysql -u root -p trilio_dms < schema.sql

db-reset:
	mysql -u root -p -e "DROP DATABASE IF EXISTS trilio_dms;"
	mysql -u root -p -e "CREATE DATABASE trilio_dms;"
	mysql -u root -p trilio_dms < schema.sql

# Development servers
run-server:
	python -m trilio_dms.server

run-example:
	python examples/example_backup_workflow.py

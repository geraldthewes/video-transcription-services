# Video Transcription Service - Makefile
.PHONY: help install test test-unit test-integration test-real-integration test-coverage clean lint format

# Default target
help:
	@echo "Video Transcription Service - Available Commands"
	@echo "================================================"
	@echo ""
	@echo "Setup Commands:"
	@echo "  install          Install production dependencies"
	@echo "  install-test     Install test dependencies"
	@echo ""
	@echo "Testing Commands:"
	@echo "  test             Run unit tests with coverage"
	@echo "  test-unit        Run only unit tests (mocked)"
	@echo "  test-integration Run mock integration tests"
	@echo "  test-real        Run REAL integration tests (requires services)"
	@echo "  test-coverage    Run tests and open coverage report"
	@echo "  test-watch       Run tests in watch mode (requires pytest-watch)"
	@echo ""
	@echo "Quality Commands:"
	@echo "  lint             Run linting (if linter configured)"
	@echo "  format           Format code (if formatter configured)"
	@echo ""
	@echo "Service Commands:"
	@echo "  build            Build Docker images"
	@echo "  up               Start services"
	@echo "  down             Stop services"
	@echo "  logs             View service logs"
	@echo ""
	@echo "Utility Commands:"
	@echo "  clean            Clean temporary files and caches"
	@echo "  health           Check service health"

# Installation
install:
	pip install -r requirements.txt

install-test:
	pip install -r requirements-test.txt

# Testing
test:
	./run_tests.sh

test-unit:
	./run_tests.sh --unit

test-integration:
	./run_tests.sh --integration

test-real:
	./run_integration_tests.sh

test-coverage:
	./run_tests.sh
	@echo "Opening coverage report..."
	@command -v open >/dev/null 2>&1 && open htmlcov/index.html || \
	command -v xdg-open >/dev/null 2>&1 && xdg-open htmlcov/index.html || \
	echo "Coverage report available at: htmlcov/index.html"

test-watch:
	@command -v ptw >/dev/null 2>&1 || (echo "Installing pytest-watch..." && pip install pytest-watch)
	ptw tests/ -- -v

# Code Quality (placeholder - add your preferred linter/formatter)
lint:
	@echo "Linting not configured. Consider adding black, flake8, or ruff."

format:
	@echo "Formatting not configured. Consider adding black or autopep8."

# Docker Services
build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

# Health Check
health:
	@echo "Checking service health..."
	@curl -s http://localhost:8000/health | python3 -m json.tool || echo "Service not responding"

# Cleanup
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf dist/
	rm -rf build/
.PHONY: help install setup lint format typecheck test validate fix clean

# Default target
help:
	@echo "Available commands:"
	@echo "  make install      - Install dependencies"
	@echo "  make setup        - Install deps + setup pre-commit hooks"
	@echo "  make lint         - Run linter (ruff check)"
	@echo "  make format       - Check formatting (ruff format)"
	@echo "  make typecheck    - Run type checker (mypy)"
	@echo "  make test         - Run tests with coverage"
	@echo "  make validate     - Run all checks (lint, format, typecheck, test)"
	@echo "  make fix          - Auto-fix linting and formatting issues"
	@echo "  make clean        - Remove cache files"

# Install dependencies
install:
	uv sync --dev

# Full setup (install + pre-commit hooks)
setup: install
	uv run pre-commit install
	@echo "Pre-commit hooks installed!"

# Linting
lint:
	uv run ruff check .

# Format check
format:
	uv run ruff format --check .

# Type checking
typecheck:
	uv run mypy scripts src

# Run tests with coverage
test:
	uv run pytest --cov --cov-report=term-missing

# Full validation (run before pushing)
validate: lint format typecheck test
	@echo "All checks passed!"

# Auto-fix issues
fix:
	uv run ruff check --fix .
	uv run ruff format .

# Clean cache files
clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

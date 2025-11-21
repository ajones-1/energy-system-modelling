# Makefile for energy-system-modelling

# Default target
.DEFAULT_GOAL := help

# Install the environment and dependencies
install:
	uv venv
	uv pip install -e .

# Run the main Python script
run:
	python src/main.py

# Run linting with ruff
lint:
	ruff check

# Run linting and fix issues automatically
lint-fix:
	ruff check --fix

# Show help
help:
	@echo "Available commands:"
	@echo "  install    - Create virtual environment and install dependencies"
	@echo "  run        - Run the main Python script"
	@echo "  lint       - Run ruff linting checks"
	@echo "  lint-fix   - Run ruff linting and auto-fix issues"
	@echo "  help       - Show this help message"

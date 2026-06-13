.PHONY: help install test test-cov lint format clean build publish

help:
	@echo "Armada - Development Commands"
	@echo ""
	@echo "install       Install development dependencies"
	@echo "test          Run tests"
	@echo "test-cov      Run tests with coverage report"
	@echo "lint          Run linting (ruff check)"
	@echo "format        Format code with ruff"
	@echo "clean         Remove build artifacts"
	@echo "build         Build distribution packages"
	@echo "publish       Build and publish to PyPI"

install:
	pip install -e ".[test]"

test:
	pytest -v

test-cov:
	pytest --cov=armada_ai --cov-report=html --cov-report=term

lint:
	ruff check armada_ai/ tests/

format:
	ruff format armada_ai/ tests/
	ruff check --fix armada_ai/ tests/

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build: clean
	python -m build

publish: build
	python -m twine upload dist/*

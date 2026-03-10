.PHONY: dev install lint test typecheck check clean

dev:
	pip install -e ".[dev,ml,app]"

install:
	pip install -e .

lint:
	ruff check src/ flows/ tests/
	ruff format --check src/ flows/ tests/

format:
	ruff check --fix src/ flows/ tests/
	ruff format src/ flows/ tests/

test:
	pytest tests/ -v

typecheck:
	mypy src/

check: lint typecheck test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +

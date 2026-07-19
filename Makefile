.PHONY: install dev format lint test clean

install:
	pip install -r backend/requirements.txt
	pip install black ruff pytest

dev:
	cd backend && uvicorn app.main:app --reload

format:
	black backend/

lint:
	ruff check backend/

test:
	pytest backend/tests/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +

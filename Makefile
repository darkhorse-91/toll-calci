.PHONY: up down build test lint db-test clean

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

test:
	pytest api/tests

lint:
	ruff check api
	mypy --strict api/app/engine
	cd web && npm run lint

db-test:
	pytest api/tests/test_db.py

clean:
	docker compose down -v

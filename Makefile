.PHONY: up down logs build shell-bot shell-core migrate encrypt-key

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

logs-bot:
	docker compose logs -f bot

logs-core:
	docker compose logs -f core

build:
	docker compose build

shell-bot:
	docker compose exec bot bash

shell-core:
	docker compose exec core sh

migrate:
	docker compose exec postgres psql -U visabot -d visabot -f /docker-entrypoint-initdb.d/001_init.sql

## Generate a new AES-256 encryption key
encrypt-key:
	python3 -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"

## Backup postgres
backup:
	docker compose exec postgres pg_dump -U visabot visabot | gzip > backup_$$(date +%Y%m%d_%H%M%S).sql.gz

restart-bot:
	docker compose restart bot

restart-core:
	docker compose restart core

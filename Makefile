.PHONY: setup up down logs ps up-infra up-backend up-frontend up-legacy \
	down-infra down-backend down-frontend down-legacy nuke

# Infrastructure, backend and frontend are independent Compose projects sharing
# one external network, so each can be rebuilt or restarted without cycling the
# others. The cost is that `depends_on` no longer spans them -- start order
# matters, and the backend blocks on the database itself via `wait_for_db`.

INFRA    := docker compose -f compose.infra.yml
BACKEND  := docker compose -f compose.backend.yml
FRONTEND := docker compose -f compose.frontend.yml
LEGACY   := docker compose -f compose.legacy.yml

# The shared network and the reports volume must exist before any project starts;
# neither is owned by a single one of them.
setup:
	docker network inspect cap-net >/dev/null 2>&1 || docker network create cap-net
	docker volume inspect cap-evaluation-data >/dev/null 2>&1 || docker volume create cap-evaluation-data

up: setup up-infra up-backend up-frontend
	@echo ""
	@echo "  frontend  http://localhost:5173"
	@echo "  backend   http://localhost:8002/api/v1/health"

up-infra: setup
	$(INFRA) up -d --build

up-backend: setup
	$(BACKEND) up -d --build

up-frontend: setup
	$(FRONTEND) up -d --build

# Pre-consolidation topology, for rollback only. See compose.legacy.yml.
up-legacy: setup
	$(LEGACY) up -d --build

# Reverse order: dependents before their dependencies.
down:
	-$(LEGACY) down
	-$(FRONTEND) down
	-$(BACKEND) down
	-$(INFRA) down

down-infra:
	$(INFRA) down

down-backend:
	$(BACKEND) down

down-frontend:
	$(FRONTEND) down

down-legacy:
	$(LEGACY) down

ps:
	@for p in cap-infra cap-backend cap-frontend cap-legacy; do \
		docker ps --filter "label=com.docker.compose.project=$$p" \
			--format "  {{.Names}}\t{{.Status}}" ; \
	done

logs:
	$(BACKEND) logs -f --tail=100

# Also removes the database, Redis and report volumes. Everything is recreated by
# the migration jobs on the next `make up`, but candidate data does not survive.
nuke: down
	-docker volume rm cap-evaluation-data
	-docker network rm cap-net

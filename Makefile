# botanical-sentinel — project management
# Run from the project root: make <target>

SHELL   := /bin/bash
.DEFAULT_GOAL := help

# ── Configurable ──────────────────────────────────────────────────────────────

PORT    ?= /dev/cu.usbmodem2101
PIO     ?= ~/.platformio/penv/bin/pio
COMPOSE := docker compose -f server/docker-compose.yml

# Docker Compose project name is derived from the compose file directory ("server"),
# so named volumes are prefixed server_ (e.g. server_timescaledb_data).

# ── Help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@printf '\n\033[1mbotanical-sentinel\033[0m  —  make <target>\n\n'
	@printf '\033[4mFirmware\033[0m\n'
	@grep -E '^(firmware|flash|monitor)[a-zA-Z_-]*:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@printf '\n\033[4mServer\033[0m\n'
	@grep -E '^(up|down|restart|build|fresh|ps)[a-zA-Z_-]*:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@printf '\n\033[4mLogs\033[0m\n'
	@grep -E '^logs[a-zA-Z_-]*:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@printf '\n\033[4mDatabase\033[0m\n'
	@grep -E '^db-[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@printf '\n\033[4mWeb\033[0m\n'
	@grep -E '^web[a-zA-Z_-]*:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@printf '\n\033[4mTests\033[0m\n'
	@grep -E '^test[a-zA-Z_-]*:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@printf '\n  PORT=$(PORT)  PIO=$(PIO)\n\n'

# ── Firmware ──────────────────────────────────────────────────────────────────

.PHONY: firmware flash flash-tft monitor

firmware: ## Build all firmware environments
	$(PIO) run --project-dir nodes/esp32-scanner

flash: ## Flash headless firmware  (override: PORT=/dev/cu.xxx)
	@printf 'Hold BOOT, press+release RESET, release BOOT — then press Enter\n'; read _
	$(PIO) run --project-dir nodes/esp32-scanner \
	  -e esp32-s3-devkitc-1-headless -t upload --upload-port $(PORT)

flash-tft: ## Flash TFT firmware  (override: PORT=/dev/cu.xxx)
	@printf 'Hold BOOT, press+release RESET, release BOOT — then press Enter\n'; read _
	$(PIO) run --project-dir nodes/esp32-scanner \
	  -e esp32-s3-devkitc-1-tft -t upload --upload-port $(PORT)

monitor: ## Open serial monitor
	$(PIO) device monitor --project-dir nodes/esp32-scanner

# ── Server — all services ─────────────────────────────────────────────────────

.PHONY: up down restart build fresh ps

up: ## Start all services
	$(COMPOSE) up -d

down: ## Stop all services
	$(COMPOSE) down

restart: ## Restart all services (no rebuild)
	$(COMPOSE) restart

build: ## Rebuild all service images
	$(COMPOSE) build

fresh: ## Full wipe — stop, remove volumes, rebuild, start
	$(COMPOSE) down -v
	$(COMPOSE) build
	$(COMPOSE) up -d

ps: ## Show running service status
	$(COMPOSE) ps

# ── Server — individual services ──────────────────────────────────────────────

.PHONY: restart-api restart-bridge

restart-api: ## Rebuild and restart only the API
	$(COMPOSE) build api
	$(COMPOSE) up -d --no-deps api

restart-bridge: ## Rebuild and restart only the MQTT bridge
	$(COMPOSE) build mqtt_bridge
	$(COMPOSE) up -d --no-deps mqtt_bridge

# ── Logs ──────────────────────────────────────────────────────────────────────

.PHONY: logs logs-api logs-bridge logs-db logs-mqtt

logs: ## Tail logs for all services
	$(COMPOSE) logs -f

logs-api: ## Tail API logs
	$(COMPOSE) logs -f api

logs-bridge: ## Tail MQTT bridge logs
	$(COMPOSE) logs -f mqtt_bridge

logs-db: ## Tail TimescaleDB logs
	$(COMPOSE) logs -f timescaledb

logs-mqtt: ## Tail Mosquitto logs
	$(COMPOSE) logs -f mosquitto

# ── Database ──────────────────────────────────────────────────────────────────

.PHONY: db-shell db-migrate db-reset

db-shell: ## Open a psql shell in TimescaleDB
	$(COMPOSE) exec timescaledb psql -U botanical botanical

db-migrate: ## Apply init.sql to existing DB (idempotent — safe to re-run)
	$(COMPOSE) exec timescaledb psql -U botanical botanical \
	  -f /docker-entrypoint-initdb.d/init.sql

db-reset: ## Wipe TimescaleDB data and reinitialise from init.sql
	$(COMPOSE) stop timescaledb mqtt_bridge api
	$(COMPOSE) rm -f timescaledb
	docker volume rm -f server_timescaledb_data
	$(COMPOSE) up -d

# ── Web ───────────────────────────────────────────────────────────────────────

.PHONY: web web-install web-build web-check

web: ## Start Vite dev server
	cd web && npm run dev

web-install: ## Install web dependencies
	cd web && npm install

web-build: ## Build for production
	cd web && npm run build

web-check: ## Run SvelteKit type check
	cd web && npm run check

# ── Tests ─────────────────────────────────────────────────────────────────────

.PHONY: test test-api test-bridge

test: test-api test-bridge ## Run all tests

test-api: ## Run API tests
	cd server/api && uv run pytest -q

test-bridge: ## Run MQTT bridge tests
	cd server/mqtt_bridge && uv run pytest -q

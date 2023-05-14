.PHONY: default banner help install build run stop restart rasa-restart rasa-stop rasa-start rasa-build seed logs ngrok pgadmin api api-stop db db-stop db-purge purge models shell-api shell-db shell-rasa shell-actions rasa-train rasa-start rasa-stop env-var

defaut: help

help:
	@make banner
	@echo "+------------------+"
	@echo "| 🏠 CORE COMMANDS |"
	@echo "+------------------+"
	@echo "make install - Install and run RasaGPT"
	@echo "make build - Build docker images"
	@echo "make run - Run RasaGPT"
	@echo "make stop - Stop RasaGPT"
	@echo "make restart - Restart RasaGPT\n"
	@echo "+--------------------+"
	@echo "| 🌍 ADMIN INTERACES |"
	@echo "+--------------------+"
	@echo "make logs - View logs via Dozzle"
	@echo "make ngrok - View ngrok dashboard"
	@echo "make pgadmin - View pgAdmin dashboard\n"
	@echo "+-----------------------+"
	@echo "| 👷 DEBUGGING COMMANDS |"
	@echo "+-----------------------+"
	@echo "make api - Run only API server"
	@echo "make models - Build Rasa models"
	@echo "make purge - Remove all docker images"
	@echo "make db-purge - Delete all data in database"
	@echo "make db-reset - Reset database to initial state"
	@echo "make shell-api - Open shell in API container"
	@echo "make shell-db - Open shell in database container"
	@echo "make shell-rasa - Open shell in Rasa container"
	@echo "make shell-actions - Open shell in Rasa actions container\n"


banner:
	@echo "\n\n-------------------------------------"
	@echo "▒█▀▀█ █▀▀█ █▀▀ █▀▀█ ▒█▀▀█ ▒█▀▀█ ▀▀█▀▀"
	@echo "▒█▄▄▀ █▄▄█ ▀▀█ █▄▄█ ▒█░▄▄ ▒█▄▄█ ░▒█░░"
	@echo "▒█░▒█ ▀░░▀ ▀▀▀ ▀░░▀ ▒█▄▄█ ▒█░░░ ░▒█░░"
	@echo "+-----------------------------------+"
	@echo "| http://RasaGPT.dev by @paulpierre |"
	@echo "+-----------------------------------+\n\n"



# ==========================
# 👷 INITIALIZATION COMMANDS
# ==========================

# ---------------------------------------
# Run this first to setup the environment
# ---------------------------------------
install:
	@make banner
	@make stop
	@make env-var
	@make rasa-train
	@make build
	@make run
	@make models
	@make rasa-restart
	@make seed
	@echo "✅ RasaGPT installed and running"

# -----------------------
# Build the docker images
# -----------------------
build:
	@echo "🏗️  Building docker images ..\n"
	@docker-compose -f docker-compose.yml build


# ================
# 🏠 CORE COMMANDS
# ================

# ---------------------------
# Startup all docker services
# ---------------------------

run:
	@echo "🚀  Starting docker-compose.yml ..\n"
	@docker-compose -f docker-compose.yml up -d

# ---------------------------
# Stop all running containers
# ---------------------------

stop:
	@echo "🔍  Stopping any running containers .. \n"
	@docker-compose -f docker-compose.yml down

# ----------------------
# Restart all containers
# ----------------------
restart:
	@echo "🔁  Restarting docker services ..\n"
	@make stop
	@make run

# ----------------------
# Restart Rasa core only
# ----------------------
rasa-restart:
	@echo "🤖  Restarting Rasa so it grabs credentials ..\n"
	@make rasa-stop
	@make rasa-start

rasa-stop:
	@echo "🤖  Stopping Rasa ..\n"
	@docker-compose -f docker-compose.yml stop rasa-core

rasa-start:
	@echo "🤖  Starting Rasa ..\n"
	@docker-compose -f docker-compose.yml up -d rasa-core

rasa-build:
	@echo "🤖  Building Rasa ..\n"
	@docker-compose -f docker-compose.yml build rasa-core

# -----------------------
# Seed database with data
# -----------------------
seed:
	@echo "🌱 Seeding database ..\n"
	@docker-compose -f docker-compose.yml exec api /app/api/wait-for-it.sh db:5432 --timeout=60 -- python3 seed.py


# =======================
# 🌍 WEB ADMIN INTERFACES
# =======================

# -------------------------
# Reverse HTTP tunnel admin
# -------------------------
ngrok:
	@echo "📡  Opening ngrok agent in the browser ..\n"
	@open http://localhost:4040

# ------------------------
# Postgres admin interface
# ------------------------
pgadmin:
	@echo "👷‍♂️  Opening PG Admin in the browser ..\n"
	@open http://localhost:5050

# ------------------------
# Container logs interface
# ------------------------
logs:
	@echo "🔍  Opening container logs in the browser ..\n"
	@open http://localhost:9999/

# =====================
# 👷 DEBUGGING COMMANDS
# =====================

# ---------------------------
# Startup just the API server
# ---------------------------
api:
	@make db
	@echo "🚀  Starting FastAPI and postgres ..\n"
	@docker-compose -f docker-compose.yml up -d api

# ------------------------
# Startup just Postgres DB
# ------------------------
db:
	@echo "🚀  Starting Postgres with pgvector ..\n"
	@docker-compose -f docker-compose.yml up -d db


db-stop:
	@echo " Stopping the database ..\n"
	@docker-compose -f docker-compose.yml down db


db-reset:
	@echo "⛔  Are you sure you want to reinitialize the database, you will lose all data? [y/N]\n"
	@read confirmation; \
	if [ "$$confirmation" = "y" ] || [ "$$confirmation" = "Y" ]; then \
		make db-purge \
		make api \
		make models \
		echo "✅ Database re-initialize"; \
	else \
		echo "Aborted."; \
	fi

	@echo " Resetting the database ..\n"
	

# -------------------------------
# Build the schema in Postgres DB
# -------------------------------
models:
	@echo "💽  Building models in Postgres ..\n"
	@docker-compose -f docker-compose.yml exec api /app/api/wait-for-it.sh db:5432 --timeout=60 -- python3 models.py

# -------------------------------
# Delete containers or bad images
# -------------------------------
purge:
	@echo "🧹  Purging all containers and images ..\n"
	@make stop
	@docker system prune -a
	@make install

# --------------------------------
# Delete the database mount volume
# --------------------------------
db-purge:
	@echo "⛔  Are you sure you want to delete all data in the database? [y/N]\n"
	@read confirmation; \
	if [ "$$confirmation" = "y" ] || [ "$$confirmation" = "Y" ]; then \
		echo "Deleting generated files .."; \
		make stop; \
		rm -rf ./mnt; \
		echo "Deleted."; \
	else \
		echo "Aborted."; \
	fi

# --------------------------------------
# Open a bash shell in the API container
# --------------------------------------
shell-api:
	@echo "💻🐢  Opening a bash shell in the RasaGPT API container ..\n"
	@if docker ps | grep chat_api > /dev/null; then \
		docker exec -it $$(docker ps | grep chat_api | tr -d '\n' | awk '{print $$1}') /bin/bash; \
	else \
		echo "Container chat_api is not running"; \
	fi

# ---------------------------------------
# Open a bash shell in the Rasa container
# ---------------------------------------
shell-rasa:
	@echo "💻🐢  Opening a bash shell in the chat_rasa_core container ..\n"
	@if docker ps | grep chat_rasa_core > /dev/null; then \
		docker exec -it $$(docker ps | grep chat_rasa_core | tr -d '\n' | awk '{print $$1}') /bin/bash; \
	else \
		echo "Container chat_rasa_core is not running"; \
	fi

# -----------------------------------------------
# Open a bash shell in the Rasa actions container
# -----------------------------------------------
shell-actions:
	@echo "💻🐢  Opening a bash shell in the chat_rasa_actions container ..\n"
	@if docker ps | grep chat_rasa_actions > /dev/null; then \
		docker exec -it $$(docker ps | grep chat_rasa_actions | tr -d '\n' | awk '{print $$1}') /bin/bash; \
	else \
		echo "Container chat_rasa_actions is not running"; \
	fi

# -------------------------------------------
# Open a bash shell in the Postgres container
# -------------------------------------------
shell-db:
	@echo "💻🐢  Opening a bash shell in the Postgres container ..\n"
	@if docker ps | grep chat_db > /dev/null; then \
		docker exec -it $$(docker ps | grep chat_db | tr -d '\n' | awk '{print $$1}') /bin/bash; \
	else \
		echo "Container chat_db is not running"; \
	fi

# ==================
# 💁 HELPER COMMANDS
# ==================

# -------------
# Check envvars
# -------------
env-var:
	@echo "🔍 Checking if envvars are set ..\n";
	@if ! test -e "./.env"; then \
		@echo "❌ .env file not found. Please copy .env-example to .env and update values"; \
		exit 1; \
    else \
        echo "✅ found .env\n"; \
    fi

# -----------------
# Train Rasa models
# -----------------
rasa-train:
	@echo "💽 Generating Rasa models ..\n"
	@make rasa-start
	@docker-compose -f docker-compose.yml exec rasa-core rasa train
	@make rasa-stop
	@echo "✅ Done\n"

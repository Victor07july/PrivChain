help:
	@echo "Usage: make [run|docker-up|docker-up-db|install-code-formatter|test|coverage-test|lint|lint-fix|new-feature|clean-migration|new-migration|revert-migration|create-admin-user|get-token]"
	@echo
	@echo 'Usage:'
	@echo '    make docker-up							Run Docker container.'
	@echo '    make docker-up-db							Run Database in Docker.'
	@echo '    make docker-prune							Delete project containers, images and volumes.'
	@echo '    make docker-reload							Shortcut for docker-prune and docker-up targets.'
	@echo '    make install-code-formatter						Install code formatter.'
	@echo '    make test								Run tests on the project.'
	@echo '    make coverage-test							Run tests on the project and generates a coverage report.'
	@echo '    make lint								Runs the linter checker.'
	@echo '    make lint-fix							Try to fix lint erros.'
	@echo '    make new-feature FEAT_NAME=<name>					Shortcut to create new feature files in the project structure.'
	@echo '    make clean-migrations MIGRATION_TITLE=<title>			Shortcut to downgrade migration to base, delete files from project structure, create a new revision, and upgrade to head.'
	@echo '    make new-migration MIGRATION_TITLE=<title>				Shortcut to create a new revision, and upgrade to head.'
	@echo '    make revert-migration						Downgrade to the previous migration.'
	@echo '    make create-admin-user USERNAME=<username> PASSWORD=<password>	Create a new admin user on the database.'
	@echo '    make get-token USERNAME=<username> PASSWORD=<password>		Create JWT token for the specified user.'
	@echo

docker-up:
	docker compose up

docker-up-db:
	docker compose up db

docker-prune:
	docker compose down
	docker rmi "$(notdir $(PWD))-backend" "$(notdir $(PWD))-backend-init"
	docker volume rm "$(notdir $(PWD))_pg-data"

docker-reload: docker-prune docker-up

install-code-formatter:
	pip install -r src/config/requirements/dev.txt
	pre-commit install

test:
	docker exec -it backend pip install -r src/config/requirements/test.txt
	docker exec -it backend python -m pytest

coverage-test:
	docker exec -it backend pytest --cov=./ --cov-report=xml

lint:
	black --check ./src

lint-fix:
	black ./src

# Alembic commands
new-feature:
	@echo Creating files...
	@mkdir ./src/$(FEAT_NAME)
	@touch ./src/$(FEAT_NAME)/__init__.py
	@mkdir ./src/$(FEAT_NAME)/test
	@touch ./src/$(FEAT_NAME)/test/__init__.py
	@mkdir ./src/$(FEAT_NAME)/v1
	@touch ./src/$(FEAT_NAME)/v1/__init__.py
	@touch ./src/$(FEAT_NAME)/v1/routes.py
	@echo "from fastapi import APIRouter\n\n$(FEAT_NAME)_v1_router = APIRouter(prefix=\"/v1/$(FEAT_NAME)\")" >> ./src/$(FEAT_NAME)/v1/routes.py
	@awk 'NR==3{print "from src.$(FEAT_NAME).v1.routes import $(FEAT_NAME)_v1_router"}1' ./src/core/api.py | tee ./src/core/api.py > /dev/null
	@echo "api_router.include_router($(FEAT_NAME)_v1_router)" >> ./src/core/api.py
	@touch ./src/$(FEAT_NAME)/exceptions.py
	@touch ./src/$(FEAT_NAME)/schemas.py
	@touch ./src/$(FEAT_NAME)/services.py
	@touch ./src/$(FEAT_NAME)/models.py
	@echo "from sqlmodel import SQLModel\n\nclass $(shell echo $(FEAT_NAME) | awk '{ print toupper($$0) }')(SQLModel, table=True):\n    pass" >> ./src/$(FEAT_NAME)/models.py
	@black ./src
	@echo "Remember to import new models inside src/config/database/migrtions/env.py, after line 13. Otherwise, they won\'t be found by almebic during new migrations."

clean-migrations:
	alembic downgrade base
	rm -rf src/config/database/migrations/versions/*
	alembic revision --autogenerate -m "$(MIGRATION_TITLE)"
	alembic upgrade head

new-migration:
	alembic revision --autogenerate -m "$(MIGRATION_TITLE)"
	alembic upgrade head

revert-migration:
	alembic downgrade -1

create-admin-user:
	source .venv/bin/activate && python3 -m src.core.scripts.create_admin $(USERNAME) $(PASSWORD)

get-token:
	source .venv/bin/activate && python3 -m src.core.scripts.get_token $(USERNAME) $(PASSWORD)

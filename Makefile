# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
# Every command a contributor needs. `make help` lists them.
.DEFAULT_GOAL := help
UV ?= uv
PORT ?= 4700

.PHONY: help sync test lint fmt typecheck check serve docker-build docker-serve

help: ## List the targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-z-]+:.*## / {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync: ## Install the package and the dev tools into .venv
	$(UV) sync --group dev

test: ## Run the tests (the browser render tests need Node 20.19+ or 22.7+)
	$(UV) run --group dev pytest

lint: ## Ruff lint and format check
	$(UV) run --group dev ruff check
	$(UV) run --group dev ruff format --check

fmt: ## Fix what ruff can fix, then format
	$(UV) run --group dev ruff check --fix
	$(UV) run --group dev ruff format

typecheck: ## mypy, strict on src/
	$(UV) run --group dev mypy

check: lint typecheck test ## Everything CI runs

serve: ## The desk on the demo project, in your browser
	$(UV) run desk --root examples/demo serve --port $(PORT) --open

docker-build: ## Build the container image (project-desk:local)
	docker build -t project-desk:local .

docker-serve: docker-build ## The demo in a container, published on 127.0.0.1 only
	docker run --rm -it -p 127.0.0.1:$(PORT):$(PORT) -e DESK_PORT=$(PORT) --user "$$(id -u):$$(id -g)" \
		-v "$(CURDIR)/examples/demo:/repo" \
		project-desk:local serve --host 0.0.0.0 --port $(PORT)

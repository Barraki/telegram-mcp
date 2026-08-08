# Dev tasks for this fork of telegram-mcp.
# Requires: make, git, uv (https://docs.astral.sh/uv/). Run `make` for the list.

UPSTREAM_URL ?= https://github.com/chigwell/telegram-mcp.git
UPSTREAM     ?= upstream
ORIGIN       ?= origin
MAIN         ?= main
BRANCH       ?= develop
UV           ?= uv

.DEFAULT_GOAL := help

.PHONY: help install hooks test cov fmt fmt-check lint check run session \
        upstream fetch sync-status sync sync-branch sync-all guard-clean clean

help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- environment -------------------------------------------------------------

install: ## Create .venv and install runtime + dev dependencies
	$(UV) sync --all-groups

hooks: ## Install the pre-commit hooks
	$(UV) run pre-commit install

# --- quality -----------------------------------------------------------------

test: ## Run the test suite
	$(UV) run pytest -q

cov: ## Run tests with a coverage report (fails under 80%)
	$(UV) run pytest --cov --cov-report=term-missing

fmt: ## Format the code with black
	$(UV) run black .

fmt-check: ## Check formatting without writing files
	$(UV) run black --check .

lint: ## Lint with flake8 (same checks as CI)
	$(UV) run flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	$(UV) run flake8 . --count --exit-zero --max-complexity=10 --max-line-length=99 --statistics

check: fmt-check lint test ## Everything CI runs, in one go

# --- running -----------------------------------------------------------------

run: ## Start the MCP server locally
	$(UV) run telegram-mcp

session: ## Generate a TELEGRAM_SESSION_STRING
	$(UV) run telegram-mcp-generate-session

# --- fork synchronisation ----------------------------------------------------

upstream: ## Add the upstream remote if it is missing
	@git remote get-url $(UPSTREAM) >/dev/null 2>&1 \
		|| git remote add $(UPSTREAM) $(UPSTREAM_URL)

fetch: upstream ## Fetch upstream and origin
	git fetch $(UPSTREAM) --prune
	git fetch $(ORIGIN) --prune

sync-status: fetch ## Show how far main has drifted from upstream/main
	@echo "upstream-only / local-only commits on $(MAIN):"
	@git rev-list --left-right --count $(UPSTREAM)/$(MAIN)...$(MAIN)
	@echo "commits on $(MAIN) that upstream does not have:"
	@git log --oneline $(UPSTREAM)/$(MAIN)..$(MAIN)

sync: guard-clean fetch ## Rebase main onto upstream/main and force-push the fork
	git switch $(MAIN)
	git rebase $(UPSTREAM)/$(MAIN)
	git push $(ORIGIN) $(MAIN) --force-with-lease
	@echo "$(MAIN) is now upstream/$(MAIN) + your own commits on top."

sync-branch: guard-clean ## Rebase BRANCH onto main and force-push it (BRANCH=develop)
	git switch $(BRANCH)
	git rebase $(MAIN)
	git push $(ORIGIN) $(BRANCH) --force-with-lease
	git switch -

sync-all: sync ## Sync main, then rebase BRANCH on top of the fresh main
	$(MAKE) sync-branch BRANCH=$(BRANCH)

guard-clean:
	@test -z "$$(git status --porcelain)" \
		|| { echo "Worktree is dirty - commit or stash first."; exit 1; }

# --- housekeeping ------------------------------------------------------------

clean: ## Remove caches, build output and coverage artefacts
	rm -rf build dist .pytest_cache .coverage coverage.xml htmlcov
	find . -path ./.venv -prune -o -name '__pycache__' -type d -print0 | xargs -0 rm -rf
	find . -path ./.venv -prune -o -name '*.pyc' -print0 | xargs -0 rm -f

# Gates for todoImplementer. `make fast` must be green before every commit.
# Heavy commands go through the shared resource cap (2 GiB, 10 % CPU, nice).
SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
CAP ?= $(HOME)/.claude/scripts/capped.sh
UV := $(CAP) uv run --frozen
MESSAGE ?=

.PHONY: fast lines private md regressions lint types test cov-clean coverage web

fast: lines private md regressions lint types test web
	@echo "make fast: green"

lines:
	@python3 scripts/check_lines.py

private:
	@python3 scripts/check_private.py $(if $(MESSAGE),--message "$(MESSAGE)")

md:
	@files=$$(git ls-files --cached --others --exclude-standard -- '*.md'); \
	if [[ -n "$$files" ]]; then bash scripts/check_md_naming.sh $$files; fi

regressions:
	@python3 scripts/check_regressions.py

lint:
	@$(UV) ruff check .
	@$(UV) ruff format --check .

# Test dirs import their helpers by bare name (pytest prepend mode), and several hold a conftest.py, so mypy
# checks each dir on its own to keep module names unique.
types:
	@$(UV) mypy --cache-dir=/dev/null server scripts tests/test_*.py
	@MYPYPATH="mcp:server" $(UV) mypy --cache-dir=/dev/null mcp/todoimpl_mcp
	@for d in tests/*/; do \
		if compgen -G "$$d*.py" > /dev/null; then MYPYPATH="$$d:server:scripts:tests/shims:deploy:mcp" $(UV) mypy --cache-dir=/dev/null "$$d"; fi; \
	done

# One pytest call per test dir (each well under the 60 s per-command cap), each writing its own coverage
# file; `coverage` merges them and still enforces fail_under = 100 over server/, scripts/, deploy/ and mcp/.
# Run one chunk with `make test-board`; all of them, then the gate, with `make test`.
CHUNKS := apikey credits board http service todo_mcp lessons usage prompts tokens tokens_audit tokens_api mcp_server deploy merge \
	runner runner_flow root
CHUNK_PATH_root := tests/test_*.py
# Every turn now starts a host process, so the runner dir is two chunks (files q-z in the second) to stay under 60 s.
CHUNK_PATH_runner := tests/runner --ignore-glob='tests/runner/test_runner_[q-z]*'
CHUNK_PATH_runner_flow := tests/runner/test_runner_[q-z]*.py

test: cov-clean
	@for c in $(CHUNKS); do $(MAKE) --no-print-directory test-$$c; done
	@$(MAKE) --no-print-directory coverage

cov-clean:
	@rm -f .coverage .coverage.*

test-%:
	@$(UV) env COVERAGE_FILE=.coverage.$* pytest $(or $(CHUNK_PATH_$*),tests/$*) --cov --cov-fail-under=0 --cov-report= -q

coverage:
	@$(UV) coverage combine .coverage.* > /dev/null
	@$(UV) coverage report

# Web gates run once the Astro app exists (pnpm only).
web:
	@if [[ -f web/package.json ]]; then \
		$(CAP) pnpm --dir web lint && $(CAP) pnpm --dir web test; \
	else echo "web: no web/package.json yet, skipped"; fi

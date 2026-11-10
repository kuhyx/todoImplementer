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
		if compgen -G "$$d*.py" > /dev/null; then MYPYPATH="$$d:server:scripts:tests/shims:tests/runner:tests/umbrella:deploy:mcp" $(UV) mypy --cache-dir=/dev/null "$$d"; fi; \
	done

# One pytest call per test dir (each well under the 60 s per-command cap), each writing its own coverage
# file; `coverage` merges them and still enforces fail_under = 100 over server/, scripts/, deploy/ and mcp/.
# Run one chunk with `make test-board`; all of them, then the gate, with `make test`.
CHUNKS := resilience gateway apikey credits board http service todo_mcp lessons usage prompts tokens tokens_audit tokens_api mcp_server deploy merge \
	runner runner_mid runner_flow runner_ship runner_tail umbrella umbrella_flow repotask repotask_flow root
CHUNK_PATH_root := tests/test_*.py
CHUNK_PATH_umbrella := tests/umbrella --ignore-glob='tests/umbrella/test_flow_*'
CHUNK_PATH_umbrella_flow := tests/umbrella/test_flow_*.py
# Every turn now starts a host process, so the runner dir is five chunks to stay under 60 s.
CHUNK_PATH_runner := tests/runner --ignore-glob='tests/runner/test_runner_[g-z]*'
CHUNK_PATH_runner_mid := tests/runner/test_runner_[g-p]*.py
CHUNK_PATH_runner_flow := tests/runner/test_runner_[qr]*.py tests/runner/test_runner_sc*.py
CHUNK_PATH_runner_ship := tests/runner/test_runner_s[e-z]*.py
CHUNK_PATH_runner_tail := tests/runner/test_runner_[t-z]*.py
# The repo-task flows start real runs and an umbrella; they get their own chunk.
CHUNK_PATH_repotask := tests/repotask --ignore=tests/repotask/test_flow.py --ignore=tests/repotask/test_umbrella_lock.py
CHUNK_PATH_repotask_flow := tests/repotask/test_flow.py tests/repotask/test_umbrella_lock.py

# Each `make test` keeps its coverage data in its own temp dir (COV_DIR): two runs in one worktree (a board
# restart re-runs the checks while the old run goes on) used to delete each other's files (T1920).
COV_DIR ?= .

test:
	@d=$$(mktemp -d "$${TMPDIR:-/tmp}/todoimpl-cov.XXXXXX"); trap 'rm -rf "$$d"' EXIT; \
	for c in $(CHUNKS); do $(MAKE) --no-print-directory test-$$c COV_DIR="$$d"; done; \
	$(MAKE) --no-print-directory coverage COV_DIR="$$d"

cov-clean:
	@rm -f .coverage .coverage.*

test-%:
	@$(UV) env COVERAGE_FILE=$(COV_DIR)/.coverage.$* pytest $(or $(CHUNK_PATH_$*),tests/$*) --cov --cov-fail-under=0 --cov-report= -q

coverage:
	@$(UV) env COVERAGE_FILE=$(COV_DIR)/.coverage coverage combine $(COV_DIR)/.coverage.* > /dev/null
	@$(UV) env COVERAGE_FILE=$(COV_DIR)/.coverage coverage report

# Web gates run once the Astro app exists (pnpm only).
web:
	@if [[ -f web/package.json ]]; then \
		$(CAP) pnpm --dir web lint && $(CAP) pnpm --dir web test; \
	else echo "web: no web/package.json yet, skipped"; fi

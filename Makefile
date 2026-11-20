# Gates for todoImplementer. `make fast` must be green before every commit.
# Heavy commands go through the shared resource cap (2 GiB, 10 % CPU, nice).
SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
CAP ?= $(HOME)/.claude/scripts/capped.sh
UV := $(CAP) uv run --frozen
MESSAGE ?=

.PHONY: fast fast-steps lines private md regressions lint types test cov-clean coverage web

# The tree's key is taken before the steps run and stored once they pass; pre-commit skips the gate for a
# tree that already passed (scripts/fast_stamp.py, T2410).
fast:
	@k=$$(python3 scripts/fast_stamp.py key); $(MAKE) --no-print-directory -j$(JOBS) -O fast-steps; \
	python3 scripts/fast_stamp.py record . "$$k"; echo "make fast: green"

fast-steps: lines private md regressions lint types test web

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

# Parallel mypy runs with a warm per-job cache under .mypy_cache/ (scripts/check_types.sh): cold ~9 s, warm ~2 s.
types:
	@$(UV) bash scripts/check_types.sh

# One pytest call per test dir (each well under the 60 s per-command cap), each writing its own coverage
# file; `coverage` merges them and still enforces fail_under = 100 over server/, scripts/, deploy/ and mcp/.
# Run one chunk with `make test-board`; all of them, then the gate, with `make test`.
CHUNKS := asks errors stall resilience gateway apikey credits board http relay sessions service todo_mcp lessons usage triage prompts tokens tokens_audit tokens_api mcp_server deploy merge \
	runner runner_cf runner_mid runner_mp runner_flow runner_ship runner_tail umbrella umbrella_flow repotask repotask_flow root
CHUNK_PATH_root := tests/test_*.py
CHUNK_PATH_umbrella := tests/umbrella --ignore-glob='tests/umbrella/test_flow_*'
CHUNK_PATH_umbrella_flow := tests/umbrella/test_flow_*.py
# Every turn now starts a host process, so the runner dir is six chunks to stay under 60 s.
CHUNK_PATH_runner := tests/runner/test_runner_[a-b]*.py
CHUNK_PATH_runner_cf := tests/runner/test_runner_[c-f]*.py
CHUNK_PATH_runner_mid := tests/runner/test_runner_[g-l]*.py
CHUNK_PATH_runner_mp := tests/runner/test_runner_[m-p]*.py
CHUNK_PATH_runner_flow := tests/runner/test_runner_[qr]*.py tests/runner/test_runner_sc*.py
CHUNK_PATH_runner_ship := tests/runner/test_runner_s[e-z]*.py
CHUNK_PATH_runner_tail := tests/runner/test_runner_[t-z]*.py
# The repo-task flows start real runs and an umbrella; they get their own chunk.
CHUNK_PATH_repotask := tests/repotask --ignore=tests/repotask/test_flow.py --ignore=tests/repotask/test_umbrella_lock.py
CHUNK_PATH_repotask_flow := tests/repotask/test_flow.py tests/repotask/test_umbrella_lock.py

# Each `make test` keeps its coverage data in its own temp dir (COV_DIR): two runs in one worktree (a board
# restart re-runs the checks while the old run goes on) used to delete each other's files (T1920).
COV_DIR ?= .
# Each chunk is one single-threaded pytest, so they run side by side; every chunk has its own coverage file
# and temp dirs (T2411: one after the other they took ~170 s, the longest quiet stretch of a card).
JOBS ?= 4

test:
	@d=$$(mktemp -d "$${TMPDIR:-/tmp}/todoimpl-cov.XXXXXX"); trap 'rm -rf "$$d"' EXIT; \
	$(MAKE) --no-print-directory -j$(JOBS) -O $(addprefix test-,$(CHUNKS)) COV_DIR="$$d"; \
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

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

# `make test` is ONE pytest run on TEST_JOBS xdist workers inside a single capped scope at the 20 % CPU / 4 GiB
# ceiling (most tests wait on processes and sockets, so more workers than cores pay off). Its coverage data
# lives in its own temp dir (COV_DIR): two runs in one worktree (a board restart re-runs the checks while the old
# run goes on) used to delete each other's files (T1920); it also holds pytest's basetemp (--basetemp), which the
# trap removes even when the run fails (T2412: a leftover basetemp once filled /tmp's
# inodes). `coverage` enforces fail_under = 100 over server/, scripts/, deploy/ and mcp/. One dir alone and serial: `make test-board`.
JOBS ?= 4  # `make fast` steps side by side (T2410)
TEST_JOBS ?= 6
TESTCAP := CAP_CPU_PCT=20 CAP_MEM=4G $(CAP) uv run --frozen
COV_DIR ?= .

test:
	@d=$$(mktemp -d "$${TMPDIR:-/tmp}/todoimpl-cov.XXXXXX"); trap 'rm -rf "$$d"' EXIT; \
	$(TESTCAP) env COVERAGE_FILE="$$d/.coverage" pytest -n $(TEST_JOBS) --dist worksteal --basetemp="$$d/tmp" --cov --cov-fail-under=0 --cov-report= -q; \
	$(MAKE) --no-print-directory coverage COV_DIR="$$d"

cov-clean:
	@rm -f .coverage .coverage.*

test-%:
	@$(UV) env COVERAGE_FILE=$(COV_DIR)/.coverage.$* pytest tests/$* --cov --cov-fail-under=0 --cov-report= -q

coverage:
	@$(UV) env COVERAGE_FILE=$(COV_DIR)/.coverage coverage report

# Web gates run once the Astro app exists (pnpm only).
web:
	@if [[ -f web/package.json ]]; then \
		$(CAP) pnpm --dir web lint && $(CAP) pnpm --dir web test; \
	else echo "web: no web/package.json yet, skipped"; fi

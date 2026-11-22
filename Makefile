# Gates for todoImplementer. `make fast` must be green before every commit.
# Heavy commands go through the shared resource cap (2 GiB, 10 % CPU, nice).
SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
CAP ?= $(HOME)/.claude/scripts/capped.sh
UV := $(CAP) uv run --frozen
MESSAGE ?=

.PHONY: fast fast-steps lines private md regressions lint types test test-shard test-cov cov-clean coverage web web-lint web-test apk

# The tree's key is taken before the steps run and stored once they pass; pre-commit skips the gate for a
# tree that already passed (scripts/fast_stamp.py, T2410). A suite that already passed on this tree (the board's
# `make test` right before its `pre-commit run --all-files`) is not run a second time (T2485).
fast:
	@k=$$(python3 scripts/fast_stamp.py key); $(MAKE) --no-print-directory -j$(JOBS) -O fast-steps; \
	python3 scripts/fast_stamp.py tested . "$$k" || $(MAKE) --no-print-directory test; \
	python3 scripts/fast_stamp.py record . "$$k"; echo "make fast: green"

# Every gate step marks the tree it passed on (KEY before, MARK after), so the steps a board session runs one
# per call count as a green `make fast` for the pre-commit hook too (T2485).
# Fail-soft: outside a git tree (a test's copy of this file) there is no key and nothing is marked.
KEY := k=$$(python3 scripts/fast_stamp.py key 2>/dev/null || true)
STAMP_MARK := [[ -z "$$k" ]] || python3 scripts/fast_stamp.py mark .
MARK = $(STAMP_MARK) $@ "$$k"

# The checks run side by side; `test` runs after them on its own, because every capped job of one session
# shares one 20 % CPU pool and the xdist run needs all of it to stay under the 60 s scope cap.
fast-steps: lines private md regressions lint types web

lines:
	@$(KEY); python3 scripts/check_lines.py; $(MARK)

private:
	@$(KEY); python3 scripts/check_private.py $(if $(MESSAGE),--message "$(MESSAGE)"); $(MARK)

md:
	@$(KEY); files=$$(git ls-files --cached --others --exclude-standard -- '*.md'); \
	if [[ -n "$$files" ]]; then bash scripts/check_md_naming.sh $$files; fi; $(MARK)

regressions:
	@$(KEY); python3 scripts/check_regressions.py; $(MARK)

lint:
	@$(KEY); $(UV) ruff check .; $(UV) ruff format --check .; $(MARK)

# Parallel mypy runs with a warm per-job cache under .mypy_cache/ (scripts/check_types.sh): cold ~9 s, warm ~2 s.
# `uv run mypy` syncs the venv and skips the build lock (a linter, T2415); the jobs then run the venv's mypy.
types:
	@$(KEY); $(UV) mypy --version >/dev/null && MYPY="$(CURDIR)/.venv/bin/mypy" $(CAP) bash scripts/check_types.sh; $(MARK)

# `make test` runs the SHARDS shards one after another, each ONE pytest run on TEST_JOBS xdist workers in its own
# capped scope at the 20 % CPU / 4 GiB ceiling (most tests wait on processes and sockets, so more workers than
# cores pay off), so each takes a build ticket of its own and none holds a slot for the whole suite (T2487: one
# run held it 58-79 s). Shards run in sequence: every capped job of one session shares one CPU pool. The coverage
# data lives in its own temp dir (COV_DIR): two runs in one worktree (a board restart re-runs the checks while the
# old run goes on) used to delete each other's files (T1920). Each shard's pytest basetemp is a temp dir its trap
# removes even when the run fails (T2412: a leftover basetemp once filled /tmp's inodes). `coverage` enforces
# fail_under = 100 over server/, scripts/, deploy/ and mcp/.
JOBS ?= 4  # `make fast` steps side by side (T2410)
TEST_JOBS ?= 6
# Lock first, scope second (T2417): the uv or pnpm shim queues on the build lock outside capped.sh's 60 s scope,
# then the tool inside starts at once under the held lock.
TESTCAP := uv run --frozen env CAP_CPU_PCT=20 CAP_MEM=4G $(CAP)
WEBCAP := pnpm --dir web exec $(CAP) pnpm
COV_DIR ?= .

test:
	@$(KEY); d=$$(mktemp -d "$${TMPDIR:-/tmp}/todoimpl-cov.XXXXXX"); trap 'rm -rf "$$d"' EXIT; \
	for s in $$(seq 1 $(SHARDS)); do $(MAKE) --no-print-directory test-shard SHARD="$$s" COV_DIR="$$d"; done; \
	$(MAKE) --no-print-directory test-cov COV_DIR="$$d"; $(MARK)

# A board session runs the suite as SHARDS calls, each under 60 s (T2416): `make test-shard SHARD=k` for k in
# 1..SHARDS into one new COV_DIR, then `make test-cov` combines exactly those SHARDS files (missing one fails) and
# enforces 100 %. Same tests as `make test`.
SHARDS ?= 6
SHARD_FILES = $(foreach k,$(shell seq 1 $(SHARDS)),$(COV_DIR)/.coverage.shard$(k)of$(SHARDS))
test-shard:
	@$(KEY); mkdir -p "$(COV_DIR)" && python3 scripts/test_shard.py $(SHARD) $(SHARDS) >/dev/null && \
	t=$$(mktemp -d "$${TMPDIR:-/tmp}/todoimpl-shard.XXXXXX") && trap 'rm -rf "$$t"' EXIT && \
	$(TESTCAP) env COVERAGE_FILE="$(COV_DIR)/.coverage.shard$(SHARD)of$(SHARDS)" TODOIMPL_TEST_SHARD=$(SHARD)/$(SHARDS) \
	pytest -n $(TEST_JOBS) --dist worksteal --basetemp="$$t/tmp" --cov --cov-fail-under=0 --cov-report= -q && \
	{ $(STAMP_MARK) shard$(SHARD)of$(SHARDS) "$$k"; }

test-cov:
	@$(KEY); for f in $(SHARD_FILES); do [[ -f "$$f" ]] || { echo "test-cov: missing $$f" >&2; exit 1; }; done; \
	COVERAGE_FILE="$(COV_DIR)/.coverage" $(UV) coverage combine -q --keep $(SHARD_FILES) && \
	$(MAKE) --no-print-directory coverage COV_DIR="$(COV_DIR)" && \
	{ $(STAMP_MARK) cov-of-$(SHARDS) "$$k"; }

cov-clean:
	@rm -f .coverage .coverage.*

test-%:
	@$(UV) env COVERAGE_FILE=$(COV_DIR)/.coverage.$* pytest tests/$* --cov --cov-fail-under=0 --cov-report= -q

coverage:
	@COVERAGE_FILE=$(COV_DIR)/.coverage $(UV) coverage report

# Web gates run once the Astro app exists (pnpm only).
# Two steps, so a session can run each in its own call under 60 s (T2411).
web: web-lint web-test

web-lint:
	@$(KEY); if [[ -f web/package.json ]]; then $(WEBCAP) lint; else echo "web: no web/package.json yet"; fi; $(MARK)

web-test:
	@$(KEY); if [[ -f web/package.json ]]; then $(WEBCAP) test; else echo "web: no web/package.json yet"; fi; $(MARK)

# Release APK for a live check (T2483): the Pixel is arm64 and the emulator x64, so no 32-bit arm AOT. A cold
# build stays under the 60 s build-slot limit. CI (app.yml) still builds every ABI for the published APK.
apk:
	@cd app && flutter build apk --release --target-platform android-arm64,android-x64 $(APK_ARGS)

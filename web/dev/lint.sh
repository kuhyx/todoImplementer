#!/bin/bash
# `pnpm lint`: one type-check beside eslint, in the one capped scope `make web-lint` opens (T2520).
#
# `astro check` covers every .ts file `tsc --noEmit` did, plus the .astro files, so tsc no longer runs. It runs
# beside eslint to use the CPU eslint leaves idle while its threads start. eslint's type-aware rules read the
# types `astro sync` writes, so sync runs first and the check skips its own. The check's report waits in a temp
# file so the two reports do not interleave. Both always run; either failing fails the step.
set -euo pipefail

cd "$(dirname "$0")/.."
report=$(mktemp "${TMPDIR:-/tmp}/web-check.XXXXXX")
trap 'rm -f "$report"' EXIT

astro sync
astro check --noSync >"$report" 2>&1 &
check=$!
# Two threads: each holds the whole TS program (about 1.5 GB), so three do not fit the 4 GiB scope. No --cache:
# it is per file, so a type change in an import leaves a stale green on the files that use it.
lint_rc=0
eslint --concurrency 2 . || lint_rc=$?
check_rc=0
wait "$check" || check_rc=$?
cat "$report"
((lint_rc == 0 && check_rc == 0))

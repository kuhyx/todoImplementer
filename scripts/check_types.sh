#!/bin/bash
# mypy over server, scripts, mcp and every test dir, in parallel with a warm per-job cache.
# Test dirs import helpers by bare name and several hold a conftest.py, so each dir is its own mypy run
# (own MYPYPATH, own cache dir under .mypy_cache/ so same-named modules never clash). Any failure fails the gate.
set -euo pipefail

readonly ROOT="${ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
readonly JOBS="${TYPES_JOBS:-4}"
readonly MYPY="${MYPY:-mypy}"  # `uv run` puts the venv first on PATH
readonly BASE_PATH="server:scripts:tests/shims:tests/runner:tests/umbrella:tests/service:tests/http:tests/peer:deploy:mcp"
out="$(mktemp -d "${TMPDIR:-/tmp}/types.XXXXXX")"
readonly out
trap 'rm -rf "$out"' EXIT
cd "$ROOT"

# One job per line: <name>|<MYPYPATH>|<mypy targets>
jobs_file="$out/jobs"
{
	echo "main||server scripts tests/test_*.py"
	echo "mcp|mcp:server|mcp/todoimpl_mcp"
	for d in tests/*/; do
		d="${d%/}"
		if compgen -G "$d/*.py" >/dev/null; then echo "${d#tests/}|$d:$BASE_PATH|$d"; fi
	done
} >"$jobs_file"

run_job() {
	local name path targets
	IFS='|' read -r name path targets <<<"$1"
	# A fresh job starts from the finished main cache (server and scripts, the bulk of every run).
	if [[ "$name" != main && ! -d ".mypy_cache/$name" && -d .mypy_cache/main ]]; then
		cp -a .mypy_cache/main ".mypy_cache/$name"
	fi
	# shellcheck disable=SC2086  # targets is a deliberate word list (globs expand here)
	MYPYPATH="$path" "$MYPY" --cache-dir=".mypy_cache/$name" $targets >"$out/$name.log" 2>&1 \
		|| { echo "$name" >>"$out/failed"; }
}
export -f run_job
export out MYPY

# main runs first alone: it fills the cache every other job is seeded from.
head -n 1 "$jobs_file" | xargs -d '\n' -I{} bash -c 'run_job "$1"' _ {}
tail -n +2 "$jobs_file" | xargs -d '\n' -P "$JOBS" -I{} bash -c 'run_job "$1"' _ {}

if [[ -f "$out/failed" ]]; then
	while read -r name; do echo "== mypy failed: $name"; cat "$out/$name.log"; done <"$out/failed"
	exit 1
fi
echo "types: $(wc -l <"$jobs_file") mypy runs ok"

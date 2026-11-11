#!/bin/bash
# Run one build tool under the board's machine-wide build lock (DOCS-turns.md, "One build at a time").
# Usage: buildlock.sh <tool> [args...]. The one-line shims in ./shims call it; the server copies it into
# the lock root next to build.lock. Only the bash process holds the lock: the tool runs without the lock fd,
# so a daemon it leaves behind can never keep the lock (and every other build) waiting.
set -euo pipefail

readonly HERE="${BASH_SOURCE[0]%/*}"
readonly SHIMS="$HERE/shims"
readonly LOCK="$HERE/build.lock"
readonly HOLDER="$HERE/build.lock.holder"
REAL=""

# find_real NAME: set REAL to the first NAME on PATH that is not one of our shims.
find_real() {
	local dir
	local -a dirs
	IFS=: read -ra dirs <<<"$PATH"
	for dir in "${dirs[@]}"; do
		[[ -n "$dir" && -x "$dir/$1" && ! -d "$dir/$1" ]] || continue
		[[ "$dir/$1" -ef "$SHIMS/$1" ]] && continue
		REAL="$dir/$1"
		return 0
	done
	return 1
}

# needs_lock ARGS...: false for a version/help probe and for a dev server, which would hold the lock for
# as long as it serves.
needs_lock() {
	if (($# == 1)); then
		case "$1" in --version | -version | version | --help | -h | help) return 1 ;; esac
	fi
	local sub="${1:-}"
	[[ "$sub" == run ]] && sub="${2:-}"
	case "$sub" in dev | serve | start | preview | watch) return 1 ;; esac
	return 0
}

main() {
	(($#)) || {
		echo "usage: buildlock.sh <tool> [args...]" >&2
		exit 2
	}
	local tool="$1"
	shift
	find_real "$tool" || {
		echo "buildlock: $tool not found on PATH" >&2
		exit 127
	}
	if [[ "${TODOIMPL_BUILD_LOCK_HELD:-}" == 1 ]] || ! needs_lock "$@"; then
		exec "$REAL" "$@"
	fi
	exec 9>>"$LOCK"
	if ! flock -n 9; then
		local held=""
		[[ -s "$HOLDER" ]] && held="$(<"$HOLDER")"
		echo "waiting for build lock held by ${held:-another build}" >&2
		flock 9
	fi
	local now cmd="$tool $*"
	printf -v now '%(%F %T)T' -1
	printf '%s (%s) since %s\n' "${TODOIMPL_BUILD_CARD:-?}" "${cmd:0:120}" "$now" >"$HOLDER.$$"
	mv -f "$HOLDER.$$" "$HOLDER"
	export TODOIMPL_BUILD_LOCK_HELD=1
	local rc=0
	"$REAL" "$@" 9>&- || rc=$?
	: >"$HOLDER"
	exit "$rc"
}

main "$@"

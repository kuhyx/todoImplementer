#!/bin/bash
# Run one build tool under the board's machine-wide build lock (DOCS-turns.md, "Three builds at a time").
# Usage: buildlock.sh <tool> [args...] | --queue | --flock <flock args>; the shims in ./shims call it. Builds
# run in arrival order through flocked tickets in build.queue, then take a free one of SLOTS slot locks
# (build.lock, build.lock.1, ...; each with <lock>.holder; protocol: buildqueue.py, T2419). Only
# this bash holds the lock fds: the tool runs without them, so a daemon it leaves never keeps the lock.
set -euo pipefail

readonly HERE="${BASH_SOURCE[0]%/*}"
readonly SHIMS="$HERE/shims"
readonly LOCK="$HERE/build.lock"
readonly HOLDER="$HERE/build.lock.holder"
readonly SLOTS="${TODOIMPL_BUILD_SLOTS:-@SLOTS@}" # filled in by buildlock.py from SLOTS; tests pin it
readonly RECHECK=2 # s a waiter blocks on one ticket or slot before it looks again (more than one slot)
SLOT_HOLDER="$HOLDER"
readonly QUEUE="$HERE/build.queue"
readonly QLOCK="$HERE/build.queue.lock"
readonly SHELLS=" bash sh zsh dash ksh fish node "
readonly SERVES=" dev serve start preview watch mcp-server "
readonly LINTERS=" @LINTERS@ " # filled in by buildlock.py from LINTERS (lanes.py shares it)
readonly PREFIXES=" env nice nohup timeout ionice stdbuf time setsid capped.sh "
readonly TEST_JOBS="${TODOIMPL_TEST_JOBS:-4}" # `flutter test` width when the caller names none (its default is half the cores)
REAL=""
BIN=""
ARGS=()
# A build is batch work: it yields CPU to claude and the desktop (idle IO class where ionice exists).
# `nice -n` adds to the shim's own niceness, which ananicy-cpp sets to -4 for every bash (T2497): 39 lands on
# 19 from any start, since the kernel clamps at 19.
LOW=(nice -n 39)
command -v ionice >/dev/null && LOW+=(ionice -c 3)
FLOCK=""
TICKET=""
TFD=""
WHAT=""
CARD="?" OWNER="?" # the ticket's card, the holder line's owner: whose (buildlock_queue.sh) sets both
CHILD=""
RELEASED=0
SAID=0
UNLOCKED=0
# shellcheck source-path=SCRIPTDIR source=buildlock_queue.sh
source "$HERE/buildlock_queue.sh"

# find_real NAME: set REAL to the first NAME on PATH that is not one of our shims.
find_real() {
	local dir
	local -a dirs
	IFS=: read -ra dirs <<<"$PATH"
	for dir in "${dirs[@]}"; do
		[[ -n "$dir" && -x "$dir/$1" && ! -d "$dir/$1" ]] || continue
		[[ "$dir/$1" -ef "$SHIMS/$1" ]] && continue
		[[ -e "$dir/../buildlock.sh" ]] && continue # another root's shim (a board session's PATH): T2391
		REAL="$dir/$1"
		return 0
	done
	return 1
}

# needs_lock TOOL ARGS...: false for a version/help probe and for a long-running server, which would hold the
# lock for as long as it serves (T2516): `dev`, `serve`, `start`, `preview`, `watch`, `mcp-server` (also after
# `run`), a package runner's `[exec|dlx|x] <bin> <one of those>`, `vite` but `vite build|optimize`, `firebase
# emulators:start` and a Firebase emulator jar (`java -jar ~/.cache/firebase/emulators/...`).
needs_lock() {
	local tool="${1##*/}" sub word bin=""
	shift
	if (($# == 1)); then
		case "$1" in --version | -version | version | --help | -h | -V | help) return 1 ;; esac
	fi
	sub="${1:-}"
	[[ "$sub" == run ]] && sub="${2:-}"
	[[ "$SERVES" == *" $sub "* ]] && return 1
	case "$tool" in
	java)
		while (($#)) && [[ "$1" != -jar ]]; do shift; done
		word="${2:-}"
		[[ "$word" == */firebase/emulators/* || "${word##*/}" == *-emulator-*.jar ]] && return 1
		return 0
		;;
	vite) bin=vite ;;
	pnpm | npm | yarn)
		[[ " run exec dlx x " == *" ${1:-} "* ]] && shift
		while [[ "${1:-}" == -* ]]; do shift; done
		[[ " add install i remove rm uninstall update up upgrade link why info view create init " == *" ${1:-} "* ]] &&
			return 0
		bin="${1:-}"
		shift || true
		;;
	esac
	[[ "$bin" == firebase && "${1:-}" == emulators:start ]] && return 1
	for word in "$@"; do
		[[ "$bin" == vite && ("$word" == build || "$word" == optimize) ]] && return 0
		[[ "$word" == -* || "$bin" == vite ]] && continue
		[[ "$SERVES" == *" $word "* ]] && return 1
		return 0
	done
	[[ "$bin" != vite ]]
}

# is_light TOOL ARGS...: true for `uv run [options] <linter> ...` and `flutter|dart analyze`: a linter only
# reads the tree (T2415).
is_light() {
	[[ "${1##*/}" == flutter || "${1##*/}" == dart ]] && [[ "${2:-}" == analyze ]] && return 0
	[[ "${1##*/}" == fvm && "${2:-}" =~ ^(flutter|dart)$ && "${3:-}" == analyze ]] && return 0
	[[ "${1##*/}" == uv && "${2:-}" == run ]] || return 1
	shift 2
	while (($#)); do
		case "$1" in
		--with | --with-editable | --with-requirements | --project | --directory | --python | -p | --extra | \
			--group | --only-group | --package | --env-file | --index | --default-index | -w) shift 2 || return 1 ;;
		-*) shift ;;
		*) [[ "$LINTERS" == *" $1 "* ]] && return 0 || return 1 ;;
		esac
	done
	return 1
}

# is_script TOOL ARGS...: true when TOOL (after env/nice/timeout-like prefixes) runs a whole script: a shell,
# python or node with a script file, `-c` or stdin, or a script given by its path. `python -m x` is one tool.
is_script() {
	local word skip=0 prefixed=0
	for word in "$@"; do
		((skip)) && skip=0 && continue
		if ((prefixed)); then
			case "$word" in
			-n | -c | -s | -k | -i | -o | -e | -p | -u) skip=1 && continue ;;
			-* | *=* | [0-9]*) continue ;;
			esac
		fi
		[[ " $PREFIXES " == *" ${word##*/} "* ]] && prefixed=1 && continue
		[[ "$word" == */* && ! -d "$word" ]] && return 0
		[[ "$SHELLS" == *" $word "* ]] && return 0
		[[ "$word" == python* || "$word" == pypy* ]] || return 1
		prefixed=0
		break
	done
	local seen=0
	for word in "$@"; do
		((seen)) || {
			[[ "$word" == python* || "$word" == pypy* ]] && seen=1
			continue
		}
		case "$word" in -m) return 1 ;; -X | -W) skip=1 ;; -c | -) return 0 ;; -*) ;; *) ((skip)) && skip=0 || return 0 ;; esac
	done
	return 0
}

# tune TOOL ARGS...: set ARGS to the whole command line, with `--concurrency=$TEST_JOBS` after `flutter test`
# (also `fvm flutter test`) unless the caller already set a width (-j, --concurrency): an unbounded run starts
# one flutter_tester per half the cores, about 12 on this PC, for every card at once.
tune() {
	local -a words=("$@")
	local at=0 i
	ARGS=("$@")
	case "${words[0]##*/}" in
	flutter) at=1 ;;
	fvm) [[ "${words[1]:-}" == flutter ]] && at=2 ;;
	esac
	((at)) && [[ "${words[at]:-}" == test ]] || return 0
	for ((i = at + 1; i < ${#words[@]}; i++)); do
		[[ "${words[i]}" == -j* || "${words[i]}" == --concurrency* ]] && return 0
	done
	ARGS=("${words[@]:0:at+1}" "--concurrency=$TEST_JOBS" "${words[@]:at+1}")
}

# release: hand the lock on (holder line, build.lock, then the ticket); once only.
release() {
	((RELEASED)) && return 0
	RELEASED=1
	: >"$SLOT_HOLDER"
	exec 9>&-
	drop_ticket
}

# cut: the server's hold ceiling saw this build do nothing for 2 min (holdceiling.py); the tool runs on.
cut() {
	release
	echo "buildlock: released the build lock: ${WHAT:0:120} did nothing for 2 min; it runs on without it" >&2
}

run_locked() {
	take_ticket
	wait_turn
	take_slot
	local now
	printf -v now '%(%F %T)T' -1
	printf '%s (%s) since %s\n' "$OWNER" "${WHAT:0:120}" "$now" >"$SLOT_HOLDER.$$"
	mv -f "$SLOT_HOLDER.$$" "$SLOT_HOLDER"
	write_ticket "$TICKET" held
	export TODOIMPL_BUILD_LOCK_HELD=1
	trap cut USR1
	trap '[[ -n "$CHILD" ]] && kill -TERM "$CHILD" 2>/dev/null' TERM INT
	trap '[[ -n "$CHILD" ]] && kill -HUP "$CHILD" 2>/dev/null' HUP
	tune "$@"
	{ exec 6<&0; } 2>/dev/null || exec 6</dev/null
	"${LOW[@]}" "$BIN" "${ARGS[@]:1}" <&6 6<&- {TFD}>&- 9>&- &
	CHILD=$!
	exec 6<&-
	local rc again
	while :; do
		rc=0
		wait "$CHILD" || rc=$?
		((rc > 128)) || break
		kill -0 "$CHILD" 2>/dev/null && continue # a trap woke us; the tool still runs
		again=0
		wait "$CHILD" 2>/dev/null || again=$?
		((again != 127)) && rc=$again
		break
	done
	release
	exit "$rc"
}

main() {
	(($#)) || {
		echo "usage: buildlock.sh <tool> [args...] | --queue | --flock <flock args>" >&2
		exit 2
	}
	find_real flock || {
		echo "buildlock: flock not found on PATH" >&2
		exit 127
	}
	FLOCK="$REAL"
	whose
	case "$1" in
	--queue) show_queue && exit 0 ;;
	--flock) shift && guard_flock "$@" ;;
	esac
	WHAT="$*"
	if [[ "${TODOIMPL_BUILD_LOCK_HELD:-}" != 1 ]] && needs_lock "$@" && is_script "$@"; then
		# Never fail a caller (a repo gate wraps itself this way): run it unlocked, shims first (T2165).
		echo "buildlock: not holding the build lock for a whole script (${WHAT:0:120}): it runs unlocked and" \
			"each heavy tool inside takes the lock itself; lock each heavy command on its own (buildlock.sh" \
			"flutter build apk), or run the script plainly with PATH passed on (systemd-run -E PATH -E" \
			"TODOIMPL_BUILD_CARD)" >&2
		[[ "$PATH" == "$SHIMS":* ]] || export PATH="$SHIMS:$PATH"
		[[ "$1" == */* ]] && exec "$@"
		UNLOCKED=1
	fi
	find_real "$1" || {
		echo "buildlock: $1 not found on PATH" >&2
		exit 127
	}
	if [[ "${TODOIMPL_BUILD_LOCK_HELD:-}" == 1 || "$UNLOCKED" == 1 ]] || ! needs_lock "$@" || is_light "$@"; then
		tune "$@"
		exec "$REAL" "${ARGS[@]:1}"
	fi
	BIN="$REAL"
	run_locked "$@"
}

main "$@"

#!/bin/bash
# Run one build tool under the board's machine-wide build lock (DOCS-turns.md, "One build at a time").
# Usage: buildlock.sh <tool> [args...] | --queue | --flock <flock args>. The one-line shims in ./shims call
# it; the server copies it into the lock root next to build.lock. Builds run in arrival order: each waiter
# holds a flocked ticket in build.queue and waits for the ticket before its own (buildqueue.py has the same
# protocol), then takes build.lock itself, which stays the one mutex. A dead waiter's ticket lock goes with
# it, so a kill or reboot never blocks the queue. Only this bash holds the lock fds: the tool runs without
# them, so a daemon it leaves behind can never keep the lock (and every other build) waiting.
set -euo pipefail

readonly HERE="${BASH_SOURCE[0]%/*}"
readonly SHIMS="$HERE/shims"
readonly LOCK="$HERE/build.lock"
readonly HOLDER="$HERE/build.lock.holder"
readonly QUEUE="$HERE/build.queue"
readonly QLOCK="$HERE/build.queue.lock"
readonly SHELLS=" bash sh zsh dash ksh fish node "
readonly PREFIXES=" env nice nohup timeout ionice stdbuf time setsid capped.sh "
REAL=""
BIN=""
FLOCK=""
TICKET=""
WHAT=""
CHILD=""
RELEASED=0
SAID=0

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
		case "$1" in --version | -version | version | --help | -h | -V | help) return 1 ;; esac
	fi
	local sub="${1:-}"
	[[ "$sub" == run ]] && sub="${2:-}"
	case "$sub" in dev | serve | start | preview | watch) return 1 ;; esac
	return 0
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

say_waiting() {
	((SAID)) && return 0
	SAID=1
	local held=""
	[[ -s "$HOLDER" ]] && held="$(<"$HOLDER")"
	echo "waiting for build lock held by ${held:-another build}; $1 ahead" >&2
}

# write_ticket PATH STATE: what `--queue` and the hold ceiling read; rewritten in place, never replaced,
# because the owner's flock is on this inode.
write_ticket() {
	local now
	printf -v now '%(%F %T)T' -1
	printf '%s %s %s (%s) since %s\n' "$$" "$2" "${TODOIMPL_BUILD_CARD:-?}" "${WHAT:0:120}" "$now" >"$1"
}

# take_ticket: join the queue under the queue lock with the next number; stale temp files go first.
take_ticket() {
	mkdir -p "$QUEUE"
	exec 7>>"$QLOCK"
	"$FLOCK" 7
	rm -f "$QUEUE"/.new.*
	local f last=0
	for f in "$QUEUE"/[0-9]*; do [[ -e "$f" ]] && last="${f##*/}"; done
	printf -v TICKET '%s/%012d' "$QUEUE" "$((10#$last + 1))"
	exec 8>"$QUEUE/.new.$$"
	"$FLOCK" 8
	write_ticket "$QUEUE/.new.$$" wait
	mv -f "$QUEUE/.new.$$" "$TICKET"
	exec 7>&-
}

# wait_turn: wait on the nearest earlier ticket until none is left; a ticket whose lock we get is dead.
wait_turn() {
	local mine="${TICKET##*/}" f prev fd ahead
	while :; do
		prev="" ahead=0
		for f in "$QUEUE"/[0-9]*; do
			[[ -e "$f" && "${f##*/}" < "$mine" ]] && prev="$f" && ahead=$((ahead + 1))
		done
		[[ -n "$prev" ]] || break
		{ exec {fd}<"$prev"; } 2>/dev/null || continue
		"$FLOCK" -n "$fd" || { say_waiting "$ahead" && "$FLOCK" "$fd"; }
		rm -f "$prev"
		exec {fd}<&-
	done
}

# release: hand the lock on (holder line, build.lock, then the ticket); once only.
release() {
	((RELEASED)) && return 0
	RELEASED=1
	: >"$HOLDER"
	exec 9>&-
	rm -f "$TICKET"
	exec 8>&-
}

# cut: the server's hold ceiling saw this build do nothing for 2 min (holdceiling.py); the tool runs on.
cut() {
	release
	echo "buildlock: released the build lock: ${WHAT:0:120} did nothing for 2 min; it runs on without it" >&2
}

show_queue() {
	local f fd n=0 line
	for f in "$QUEUE"/[0-9]*; do
		[[ -e "$f" ]] || continue
		{ exec {fd}<"$f"; } 2>/dev/null || continue
		if "$FLOCK" -n "$fd"; then
			rm -f "$f"
		else
			read -r line <"$f" || true
			n=$((n + 1))
			read -r pid rest <<<"$line" || true
			echo "$n ${rest:-wait ? () since ?} pid ${pid:-0}"
		fi
		exec {fd}<&-
	done
}

# guard_flock ARGS...: the `flock` shim; a flock on the lock, its holder or its queue jumps the queue.
guard_flock() {
	local word target
	for word in "$@"; do
		target="$word"
		[[ "$word" =~ ^[0-9]+$ ]] && target="/proc/$$/fd/$word"
		[[ -e "$target" ]] && target="$(realpath -- "$target")" || target="$(realpath -m -- "$target")"
		case "$target" in "$(realpath -m -- "$LOCK")"* | "$(realpath -m -- "$QUEUE")"*)
			echo "buildlock: refusing flock on the board's build lock: it serves builds in arrival order, so run" \
				"each heavy command plainly (the shims queue it) or as buildlock.sh <tool> [args...]; see the" \
				"queue with buildlock.sh --queue" >&2
			exit 2
			;;
		esac
	done
	exec "$FLOCK" "$@"
}

run_locked() {
	take_ticket
	wait_turn
	exec 9>>"$LOCK"
	"$FLOCK" -n 9 || { say_waiting 0 && "$FLOCK" 9; }
	local now
	printf -v now '%(%F %T)T' -1
	printf '%s (%s) since %s\n' "${TODOIMPL_BUILD_CARD:-?}" "${WHAT:0:120}" "$now" >"$HOLDER.$$"
	mv -f "$HOLDER.$$" "$HOLDER"
	write_ticket "$TICKET" held
	export TODOIMPL_BUILD_LOCK_HELD=1
	trap cut USR1
	trap '[[ -n "$CHILD" ]] && kill -TERM "$CHILD" 2>/dev/null' TERM INT
	trap '[[ -n "$CHILD" ]] && kill -HUP "$CHILD" 2>/dev/null' HUP
	shift
	{ exec 6<&0; } 2>/dev/null || exec 6</dev/null
	"$BIN" "$@" <&6 6<&- 7>&- 8>&- 9>&- &
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
	case "$1" in
	--queue) show_queue && exit 0 ;;
	--flock) shift && guard_flock "$@" ;;
	esac
	WHAT="$*"
	if [[ "${TODOIMPL_BUILD_LOCK_HELD:-}" != 1 ]] && needs_lock "${@:2}" && is_script "$@"; then
		echo "buildlock: refusing to hold the build lock for a whole script (${WHAT:0:120}): lock each heavy" \
			"command on its own (buildlock.sh flutter build apk), or run the script plainly with PATH passed on" \
			"(systemd-run -E PATH -E TODOIMPL_BUILD_CARD) so each heavy tool inside takes the lock itself" >&2
		exit 2
	fi
	find_real "$1" || {
		echo "buildlock: $1 not found on PATH" >&2
		exit 127
	}
	if [[ "${TODOIMPL_BUILD_LOCK_HELD:-}" == 1 ]] || ! needs_lock "${@:2}"; then
		shift
		exec "$REAL" "$@"
	fi
	BIN="$REAL"
	run_locked "$@"
}

main "$@"

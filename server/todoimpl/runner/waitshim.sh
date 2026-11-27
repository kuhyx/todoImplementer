#!/bin/bash
# `timeout` and `tail` shim for board sessions (T2591): one call waits at most 40 s. A session that waits on a
# job with `timeout 2400 tail --pid=...`, or follows a log with `tail -F`, sat quiet past the 60 s stall mark
# and filed `stall-job-tail`, whatever the standing prompt said. Here a long `timeout` around a waiter (tail,
# inotifywait, sleep, gh ... watch, journalctl) is cut to 40 s, and a `tail` that follows a file ends after
# 40 s; the caller checks the job and waits again. Every other command passes through untouched.
set -euo pipefail

readonly CAP=40

# find_real NAME: the first NAME on PATH that is not a board shim.
find_real() {
	local dir
	local -a dirs
	IFS=: read -ra dirs <<<"${PATH:-}"
	for dir in "${dirs[@]}"; do
		[[ -n "$dir" && -x "$dir/$1" && ! -d "$dir/$1" ]] || continue
		[[ "$dir/$1" -ef "$0" || -e "$dir/../buildlock.sh" ]] && continue
		echo "$dir/$1"
		return 0
	done
	echo "$1: not found on PATH" >&2
	return 127
}

note() {
	echo "board: $1 capped at $CAP s (one call waits at most $CAP s); check the job, then wait again" >&2
}

# over DURATION: true when a timeout duration (N, N.N, with s/m/h/d) is longer than the cap.
over() {
	local n="$1" mult=1
	case "$n" in
	*s) n="${n%s}" ;;
	*m) n="${n%m}" mult=60 ;;
	*h) n="${n%h}" mult=3600 ;;
	*d) n="${n%d}" mult=86400 ;;
	esac
	[[ "$n" =~ ^[0-9]*\.?[0-9]+$ ]] || return 1
	awk -v n="$n" -v m="$mult" -v cap="$CAP" 'BEGIN { exit !(n * m > cap) }'
}

# waiter ARGS...: true when the command only waits (it ends when something else happens).
waiter() {
	local arg
	case "${1##*/}" in
	tail | inotifywait | inotifywatch | sleep) return 0 ;;
	journalctl) for arg in "${@:2}"; do [[ "$arg" == -f || "$arg" == --follow ]] && return 0; done ;;
	gh) for arg in "${@:2}"; do [[ "$arg" == watch || "$arg" == --watch ]] && return 0; done ;;
	esac
	return 1
}

# follows ARGS...: true when tail's arguments follow a file.
follows() {
	local arg i c
	for arg in "$@"; do
		case "$arg" in
		--) return 1 ;;
		-f | -F | --follow | --follow=*) return 0 ;;
		--*) ;;
		-?*)
			for ((i = 1; i < ${#arg}; i++)); do
				c="${arg:i:1}"
				[[ "$c" == [fF] ]] && return 0
				[[ "$c" == [ncs] ]] && break # the rest of the word is that option's value
			done
			;;
		esac
	done
	return 1
}

run_timeout() {
	local real
	real="$(find_real timeout)"
	local -a opts=()
	while (($#)); do
		case "$1" in
		-k | -s | --kill-after | --signal) opts+=("$1" "${2-}") && shift 2 ;;
		--) opts+=("$1") && shift && break ;;
		-*) opts+=("$1") && shift ;;
		*) break ;;
		esac
	done
	if (($# >= 2)) && over "$1" && waiter "${@:2}"; then
		note "wait on ${2##*/}"
		exec "$real" "${opts[@]}" "$CAP" "${@:2}"
	fi
	exec "$real" "${opts[@]}" "$@"
}

run_tail() {
	local real
	real="$(find_real tail)"
	if follows "$@"; then
		note "tail -f"
		exec "$(find_real timeout)" "$CAP" "$real" "$@"
	fi
	exec "$real" "$@"
}

case "${0##*/}" in
timeout) run_timeout "$@" ;;
*) run_tail "$@" ;;
esac
exit $?

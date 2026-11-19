#!/bin/bash
# The build lock's ticket queue and the `flock` guard, sourced by buildlock.sh (same protocol: buildqueue.py).
# A waiter takes the next numbered ticket in build.queue under build.queue.lock and holds an flock on it while
# it waits and while it builds; it waits on the nearest earlier ticket until none is left. A ticket whose flock
# we get is dead (killed, rebooted) and is removed, except a board check's (` board`), kept for its restarted
# server (T2168). The fds here are picked by bash ({var}), so a caller's fd 7 or 8 is never clobbered.
# Needs from the wrapper: QUEUE QLOCK LOCK HOLDER FLOCK WHAT, and the globals TICKET TFD SAID.

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
	local qfd f last=0
	mkdir -p "$QUEUE"
	exec {qfd}>>"$QLOCK"
	"$FLOCK" "$qfd"
	rm -f "$QUEUE"/.new.*
	for f in "$QUEUE"/[0-9]*; do [[ -e "$f" ]] && last="${f##*/}"; done
	printf -v TICKET '%s/%012d' "$QUEUE" "$((10#$last + 1))"
	exec {TFD}>"$QUEUE/.new.$$"
	"$FLOCK" "$TFD"
	write_ticket "$QUEUE/.new.$$" wait
	mv -f "$QUEUE/.new.$$" "$TICKET"
	exec {qfd}>&-
}

# wait_turn: wait on the nearest earlier ticket until none is left; a kept board place is passed over.
wait_turn() {
	local mine="${TICKET##*/}" f prev fd ahead line skip=" "
	while :; do
		prev="" ahead=0
		for f in "$QUEUE"/[0-9]*; do
			[[ -e "$f" && "${f##*/}" < "$mine" && "$skip" != *" ${f##*/} "* ]] && prev="$f" && ahead=$((ahead + 1))
		done
		[[ -n "$prev" ]] || break
		{ exec {fd}<"$prev"; } 2>/dev/null || continue
		"$FLOCK" -n "$fd" || { say_waiting "$ahead" && "$FLOCK" "$fd" && skip=" "; }
		read -r line <&"$fd" || true
		if [[ "$line" == *" board" ]]; then skip+="${prev##*/} "; else rm -f "$prev"; fi
		exec {fd}<&-
	done
}

drop_ticket() {
	rm -f "$TICKET"
	exec {TFD}>&-
}

# live_ticket: true when any ticket's owner is alive (waiting or building).
live_ticket() {
	local f fd
	for f in "$QUEUE"/[0-9]*; do
		[[ -e "$f" ]] || continue
		{ exec {fd}<"$f"; } 2>/dev/null || continue
		if ! "$FLOCK" -n "$fd"; then
			exec {fd}<&-
			return 0
		fi
		exec {fd}<&-
	done
	return 1
}

show_queue() {
	local f fd n=0 line pid rest
	for f in "$QUEUE"/[0-9]*; do
		[[ -e "$f" ]] || continue
		{ exec {fd}<"$f"; } 2>/dev/null || continue
		if "$FLOCK" -n "$fd"; then
			read -r line <&"$fd" || true
			[[ "$line" == *" board" ]] || rm -f "$f"
		else
			read -r line <"$f" || true
			n=$((n + 1))
			read -r pid rest <<<"$line" || true
			echo "$n ${rest:-wait ? () since ?} pid ${pid:-0}"
		fi
		exec {fd}<&-
	done
}

# guard_flock ARGS...: the `flock` shim (T2167). A hand-held flock on build.lock queues like any build: a
# blocking one waits for its turn, then takes the lock (it stays on the caller's fd); `-n` fails while anyone
# is queued. A flock on the holder file or the queue is refused. Under a held lock it runs as asked.
guard_flock() {
	[[ "${TODOIMPL_BUILD_LOCK_HELD:-}" == 1 ]] && exec "$FLOCK" "$@"
	local word target lock=0 nonblock=0 rc=0
	for word in "$@"; do
		[[ "$word" == -u || "$word" == --unlock ]] && exec "$FLOCK" "$@"
		[[ "$word" == --nonblock || ("$word" == -[!-]* && "$word" == *n*) ]] && nonblock=1
		target="$word"
		[[ "$word" =~ ^[0-9]+$ ]] && target="/proc/$$/fd/$word"
		[[ -e "$target" ]] && target="$(realpath -- "$target")" || target="$(realpath -m -- "$target")"
		case "$target" in
		"$(realpath -m -- "$LOCK")") lock=1 ;;
		"$(realpath -m -- "$HOLDER")"* | "$(realpath -m -- "$QUEUE")"*)
			echo "buildlock: refusing flock on the build lock's holder or queue files: run each heavy command" \
				"plainly (the shims queue it) or as buildlock.sh <tool> [args...]; see the queue with" \
				"buildlock.sh --queue" >&2
			exit 2
			;;
		esac
	done
	((lock)) || exec "$FLOCK" "$@"
	if ((nonblock)); then
		live_ticket && exit 1
		exec "$FLOCK" "$@"
	fi
	WHAT="flock $*"
	take_ticket
	wait_turn
	"$FLOCK" "$@" {TFD}>&- || rc=$?
	drop_ticket
	exit "$rc"
}

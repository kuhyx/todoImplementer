#!/bin/bash
# The build lock's ticket queue and the `flock` guard, sourced by buildlock.sh (same protocol: buildqueue.py).
# A waiter takes the next numbered ticket in build.queue under build.queue.lock and holds an flock on it while
# it waits and while it builds; it goes once fewer than SLOTS live tickets are ahead (T2419), then takes a free
# slot lock (take_slot). A ticket whose flock
# we get is dead (killed, rebooted) and is removed, except a board check's (` board`), kept for its restarted
# server (T2168). The fds here are picked by bash ({var}), so a caller's fd 7 or 8 is never clobbered.
# Needs from the wrapper: QUEUE QLOCK LOCK HOLDER SLOTS RECHECK FLOCK WHAT, and the globals TICKET TFD SAID
# SLOT_HOLDER.

# slot_lock N: print slot N's lock file (slot 0 is build.lock, which old wrappers take).
slot_lock() {
	if (($1)); then echo "$LOCK.$1"; else echo "$LOCK"; fi
}

# limit: the flock timeout words for one wait: none with one slot (wait as long as it takes).
limit() {
	((SLOTS > 1)) && echo "-w $RECHECK"
	return 0
}

say_waiting() {
	((SAID)) && return 0
	SAID=1
	local held="" n f
	for ((n = 0; n < SLOTS; n++)); do
		f="$(slot_lock "$n").holder"
		[[ -s "$f" ]] && held+="${held:+ + }$(<"$f")"
	done
	echo "waiting for build lock held by ${held:-another build}; $1 ahead" >&2
}

# take_slot: take a free slot lock on fd 9 and set SLOT_HOLDER; all busy (an old wrapper, a hand-held lock):
# wait on slot 0, looking again every RECHECK s when there is more than one slot.
take_slot() {
	local n lock
	while :; do
		for ((n = 0; n < SLOTS; n++)); do
			lock="$(slot_lock "$n")"
			exec 9>>"$lock"
			if "$FLOCK" -n 9; then
				SLOT_HOLDER="$lock.holder"
				return 0
			fi
			exec 9>&-
		done
		say_waiting 0
		exec 9>>"$LOCK"
		# shellcheck disable=SC2046 # limit prints flock words
		if "$FLOCK" $(limit) 9; then
			SLOT_HOLDER="$HOLDER"
			return 0
		fi
		exec 9>&-
	done
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

# wait_turn: wait until fewer than SLOTS live tickets are ahead. Each look settles the dead ones (removed; a
# kept board place is passed over). With one slot it blocks on the nearest live ticket until it ends; with
# more, for RECHECK s, then it counts again, so any build that ends lets it on (T2420).
wait_turn() {
	local mine="${TICKET##*/}" f prev fd ahead line skip=" "
	while :; do
		prev="" ahead=0
		for f in "$QUEUE"/[0-9]*; do
			[[ -e "$f" && "${f##*/}" < "$mine" && "$skip" != *" ${f##*/} "* ]] || continue
			{ exec {fd}<"$f"; } 2>/dev/null || continue
			if "$FLOCK" -n "$fd"; then
				read -r line <&"$fd" || true
				if [[ "$line" == *" board" ]]; then skip+="${f##*/} "; else rm -f "$f"; fi
			else
				prev="$f" ahead=$((ahead + 1))
			fi
			exec {fd}<&-
		done
		((ahead >= SLOTS)) || break
		{ exec {fd}<"$prev"; } 2>/dev/null || continue
		say_waiting "$ahead"
		# shellcheck disable=SC2046 # limit prints flock words
		"$FLOCK" $(limit) "$fd" && skip=" "
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
		"$(realpath -m -- "$LOCK")" | "$(realpath -m -- "$LOCK")".[0-9]) lock=1 ;;
		"$(realpath -m -- "$HOLDER")"* | "$(realpath -m -- "$QUEUE")"* | "$(realpath -m -- "$LOCK")".*.holder*)
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

#!/bin/bash
# systemd-run shim for board sessions (T2401, cardslice.py): a job a session starts in the shared board slice
# (`--slice=todoimpl.slice`) joins its own card's slice (`$TODOIMPL_SLICE`) instead, so one card's job is
# capped on its own and can never throttle every other card. Anything else passes through untouched: a unit
# with no slice may be a real service a deploy starts, which a card's Cancel must not stop.
set -euo pipefail

readonly PARENT=todoimpl.slice

# find_real: the first systemd-run on PATH that is not a board shim.
find_real() {
	local dir
	local -a dirs
	IFS=: read -ra dirs <<<"${PATH:-}"
	for dir in "${dirs[@]}"; do
		[[ -n "$dir" && -x "$dir/systemd-run" && ! -d "$dir/systemd-run" ]] || continue
		[[ "$dir/systemd-run" -ef "$0" || -e "$dir/../buildlock.sh" ]] && continue
		echo "$dir/systemd-run"
		return 0
	done
	return 1
}

real="$(find_real)" || {
	echo "systemd-run: not found on PATH" >&2
	exit 127
}
slice="${TODOIMPL_SLICE:-}"
args=()
prev=""
opts=1
for arg in "$@"; do
	if [[ -n "$slice" && "$opts" == 1 ]]; then
		if [[ "$arg" == "--slice=$PARENT" ]]; then
			arg="--slice=$slice"
		elif [[ "$prev" == --slice && "$arg" == "$PARENT" ]]; then
			arg="$slice"
		fi
		[[ "$arg" == -- ]] && opts=0
	fi
	args+=("$arg")
	prev="$arg"
done
exec "$real" "${args[@]}"

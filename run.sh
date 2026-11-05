#!/bin/bash
# One command: install tools, build, (re)start the todoImplementer server unit, open the page.
# Every step aborts the script on failure, so the browser only opens on a live server.
#
#   ./run.sh
#
# Env: TODOIMPL_APP_PORT (default 8786), TODOIMPL_URL (page to open),
#      RUN_WAIT_TRIES (default 60) x RUN_WAIT_INTERVAL (default 0.5 s) bound the /version wait.
# Needs: pacman + sudo (only when uv or pnpm is missing), systemctl --user, curl, xdg-open.
set -euo pipefail

# shellcheck source=deploy/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/deploy/lib.sh"

readonly UNIT=todoimplementer.service
readonly PREVIEW_UNIT=todoimplementer-preview.service
readonly URL="${TODOIMPL_URL:-http://127.0.0.1:${APP_PORT}/}"
readonly WAIT_TRIES="${RUN_WAIT_TRIES:-60}"
readonly WAIT_INTERVAL="${RUN_WAIT_INTERVAL:-0.5}"

step() {
	echo "run.sh: $*"
}

# ensure_tools <tool>...: pacman-install only the tools that are missing.
ensure_tools() {
	local -a missing=()
	local tool
	for tool in "$@"; do
		command -v "$tool" >/dev/null || missing+=("$tool")
	done
	((${#missing[@]})) || return 0
	step "installing ${missing[*]}"
	sudo pacman -S --needed --noconfirm "${missing[@]}"
	for tool in "${missing[@]}"; do
		command -v "$tool" >/dev/null || die "$tool still missing after pacman"
	done
}

build_toolchain() {
	local python_version build_id
	python_version="$(<"${REPO_DIR}/.python-version")"
	build_id="${TODOIMPL_BUILD_ID:-$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)}"
	step "python ${python_version}"
	uv python install "$python_version"
	step "uv sync"
	(cd "$REPO_DIR" && uv sync --frozen)
	step "web install + build"
	TODOIMPL_BUILD_ID="$build_id" pnpm --dir "${REPO_DIR}/web" install --frozen-lockfile
	TODOIMPL_BUILD_ID="$build_id" pnpm --dir "${REPO_DIR}/web" build
}

restart_server() {
	step "installing ${UNIT}"
	install_unit "$UNIT"
	systemctl --user daemon-reload
	# The transient preview unit holds the port the real unit needs.
	if systemctl --user is-active --quiet "$PREVIEW_UNIT"; then
		step "stopping ${PREVIEW_UNIT}"
		systemctl --user stop "$PREVIEW_UNIT"
	fi
	systemctl --user enable --now "$UNIT"
	# restart: an already-active unit must pick up the fresh build.
	systemctl --user restart "$UNIT"
}

# wait_ready: poll /version until it answers 200; dump the journal and fail on timeout.
wait_ready() {
	local i
	step "waiting for /version on port ${APP_PORT}"
	for ((i = 0; i < WAIT_TRIES; i++)); do
		if curl -fsS -o /dev/null --max-time 2 "http://127.0.0.1:${APP_PORT}/version" 2>/dev/null; then
			return 0
		fi
		sleep "$WAIT_INTERVAL"
	done
	journalctl --user -u "$UNIT" -n 20 --no-pager || true
	die "${UNIT} never answered /version"
}

main() {
	ensure_tools uv pnpm
	build_toolchain
	restart_server
	wait_ready
	step "opening ${URL}"
	# Detached and silenced: a freshly launched browser would otherwise hold this terminal and flood it.
	setsid -f xdg-open "$URL" </dev/null >/dev/null 2>&1
}

main "$@"

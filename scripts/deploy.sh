#!/bin/bash
# Deploy this checkout to the live todoImplementer user unit: tools, build, install unit, restart, verify.
# Safe at any time: claude turns are their own systemd units and the new server adopts them (DOCS-spec.md,
# "Turns outlive the server"), so running sessions are not touched. Never opens a browser (run.sh does).
#
#   scripts/deploy.sh
#
# Env: TODOIMPL_APP_PORT (default 8786), TODOIMPL_BUILD_ID (stamps the web build only),
#      RUN_WAIT_TRIES (default 60) x RUN_WAIT_INTERVAL (default 0.5 s) bound the wait for /version.
# Needs: pacman + sudo (only when uv, pnpm or jq is on neither PATH nor a per-user bin dir), systemctl --user, curl, git.
# Success means /version reports `git rev-parse --short HEAD` of this checkout: the server computes that
# itself at start (http/main.py), so TODOIMPL_BUILD_ID is not what /version says.
set -euo pipefail

# shellcheck source=deploy/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/../deploy/lib.sh"

readonly UNIT=todoimplementer.service
readonly PREVIEW_UNIT=todoimplementer-preview.service
# The cap every board unit runs under (deploy/todoimpl.slice, T1982).
readonly SLICE=todoimpl.slice
readonly WAIT_TRIES="${RUN_WAIT_TRIES:-60}"
readonly WAIT_INTERVAL="${RUN_WAIT_INTERVAL:-0.5}"

step() {
	echo "deploy.sh: $*"
}

# add_user_bin_dirs: a systemd-run or cron environment lacks the per-user install dirs (uv lives in
# ~/.local/bin), so a tool there looked missing and got pacman-installed. Appended, so system tools and test
# stubs earlier on PATH still win.
add_user_bin_dirs() {
	local dir
	for dir in "${HOME}/.local/bin" "${HOME}/.cargo/bin" "${HOME}/.local/share/pnpm"; do
		[[ -d "$dir" && ":${PATH}:" != *":${dir}:"* ]] && PATH="${PATH}:${dir}"
	done
	export PATH
	return 0
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

head_build() {
	git -C "$REPO_DIR" rev-parse --short HEAD
}

build_toolchain() {
	local python_version build_id
	python_version="$(<"${REPO_DIR}/.python-version")"
	build_id="${TODOIMPL_BUILD_ID:-$(head_build 2>/dev/null || echo unknown)}"
	step "python ${python_version}"
	uv python install "$python_version"
	step "uv sync"
	(cd "$REPO_DIR" && uv sync --frozen)
	step "web install + build"
	TODOIMPL_BUILD_ID="$build_id" pnpm --dir "${REPO_DIR}/web" install --frozen-lockfile
	TODOIMPL_BUILD_ID="$build_id" pnpm --dir "${REPO_DIR}/web" build
}

# ensure_sdk_venv: the Claude Agent SDK lives in its own venv (credit turns only), exact-pinned in
# deploy/requirements-sdk.txt; the server itself stays stdlib-only. Idempotent: the venv is created once and
# `uv pip install` is a no-op while the pin is met.
ensure_sdk_venv() {
	local venv="${TODOIMPL_SDK_VENV:-${HOME}/.local/share/todoImplementer/sdk-venv}"
	step "agent sdk venv ${venv}"
	if [[ ! -x "${venv}/bin/python" ]]; then
		uv venv --quiet --python "$(<"${REPO_DIR}/.python-version")" "$venv"
	fi
	uv pip install --quiet --python "${venv}/bin/python" -r "${DEPLOY_DIR}/requirements-sdk.txt"
}

restart_server() {
	step "installing ${UNIT} and ${SLICE}"
	install_unit "$UNIT"
	install_unit "$SLICE"
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

# served_build: the build /version reports, empty while nothing answers.
served_build() {
	curl -fsS --max-time 2 "http://127.0.0.1:${APP_PORT}/version" 2>/dev/null | jq -r '.build // empty' 2>/dev/null || true
}

# wait_for_build <expected>: poll /version until it reports that build; dump the journal and fail on timeout.
wait_for_build() {
	local expected="$1" served="" i
	step "waiting for /version on port ${APP_PORT} to report ${expected}"
	for ((i = 0; i < WAIT_TRIES; i++)); do
		served="$(served_build)"
		[[ "$served" == "$expected" ]] && return 0
		sleep "$WAIT_INTERVAL"
	done
	journalctl --user -u "$UNIT" -n 20 --no-pager || true
	if [[ -z "$served" ]]; then
		die "${UNIT} never answered /version"
	fi
	die "${UNIT} serves build ${served}, expected ${expected}: the new code is not what is running"
}

# ensure_linger: without lingering the user manager (and so the board and its turn units) only exists while kuhy
# is logged in; with it, everything is back after a reboot even before a login (DOCS-resilience.md).
ensure_linger() {
	[[ "$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null)" == yes ]] && return 0
	step "turning lingering on for $(id -un)"
	loginctl enable-linger "$(id -un)" || true
	[[ "$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null)" == yes ]] || die "lingering is still off for $(id -un): the board will not start at boot"
	step "lingering on"
}

main() {
	add_user_bin_dirs
	ensure_tools uv pnpm jq
	local expected
	expected="$(head_build)"
	build_toolchain
	ensure_sdk_venv
	ensure_linger
	restart_server
	wait_for_build "$expected"
	step "serving build ${expected}"
}

main "$@"

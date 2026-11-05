#!/bin/bash
# Build the web UI, install + enable the systemd --user unit, restart it, and prove the
# live server runs this checkout (GET /version == git short hash). Idempotent.
#
#   deploy/install.sh              build, install, enable, (re)start, verify
#   deploy/install.sh --dry-run    verify the unit and preconditions, change nothing
#   deploy/install.sh --skip-build reuse web/dist
#   deploy/install.sh --with-token-ingest  also install token-ingest.{service,timer} and
#                                          disable the old token-dashboard-ingest.timer
#
# Needs: systemctl, pnpm, curl, ss, git, python3. KillMode=process keeps runs alive.
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

readonly UNIT=todoimplementer.service
DRY_RUN=0
SKIP_BUILD=0
WITH_INGEST=0
readonly OLD_INGEST=token-dashboard-ingest.timer
for arg in "$@"; do
	case "$arg" in
	--dry-run) DRY_RUN=1 ;;
	--skip-build) SKIP_BUILD=1 ;;
	--with-token-ingest) WITH_INGEST=1 ;;
	*) die "usage: $0 [--dry-run] [--skip-build] [--with-token-ingest]" ;;
	esac
done

for tool in systemctl pnpm curl ss git python3; do
	command -v "$tool" >/dev/null || die "$tool is required"
done

build_id="${TODOIMPL_BUILD_ID:-$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || true)}"
[[ -n "$build_id" ]] || die "no git commit yet in $REPO_DIR: cannot stamp a build id"

# Port guard: a listener is fine only if it is our own (active) unit.
listener="$(listener_on "$APP_PORT" || true)"
state="$(systemctl --user is-active "$UNIT" || true)"
if [[ -n "$listener" && "$state" != active ]]; then
	die "port ${APP_PORT} is held by something that is not ${UNIT}: ${listener}"
fi

if ((DRY_RUN)); then
	if command -v systemd-analyze >/dev/null; then
		systemd-analyze --user verify "${DEPLOY_DIR}/${UNIT}" || die "unit does not verify"
	fi
	((!WITH_INGEST)) || echo "dry run: would install token-ingest.{service,timer}, enable the timer, disable ${OLD_INGEST}"
	echo "dry run ok: would build ${build_id}, install ${UNIT_DIR}/${UNIT}, restart (state: ${state})"
	exit 0
fi

if ((!SKIP_BUILD)); then
	TODOIMPL_BUILD_ID="$build_id" pnpm --dir "${REPO_DIR}/web" install --frozen-lockfile
	TODOIMPL_BUILD_ID="$build_id" pnpm --dir "${REPO_DIR}/web" build
fi

install_unit "$UNIT"
systemctl --user daemon-reload
systemctl --user enable "$UNIT"
# restart (not start): an already-active unit must pick up the new code.
systemctl --user restart "$UNIT"

if ((WITH_INGEST)); then
	install_unit token-ingest.service
	install_unit token-ingest.timer
	systemctl --user daemon-reload
	systemctl --user disable --now "$OLD_INGEST" || true # replaced by token-ingest.timer
	systemctl --user enable --now token-ingest.timer
fi

# Event wait: curl retries until the listener answers (connection refused is retried).
body="$(curl -fsS --max-time 5 --retry 20 --retry-delay 1 --retry-connrefused \
	"http://127.0.0.1:${APP_PORT}/version")"
live="$(printf '%s' "$body" | deploy_tools version-match "$build_id")"
started="$(systemctl --user show "$UNIT" -p ExecMainStartTimestamp --value)"
echo "live: ${UNIT} build ${live}, started ${started}"
[[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null || true)" == yes ]] ||
	echo "warning: linger is off; the unit will not start at boot (loginctl enable-linger)" >&2

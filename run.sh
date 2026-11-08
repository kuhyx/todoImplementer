#!/bin/bash
# One command: deploy (scripts/deploy.sh) and open the page. Aborts on any failed step, so the browser only
# opens on a live server that runs this checkout's code.
#
#   ./run.sh
#
# Env: TODOIMPL_APP_PORT (default 8786), TODOIMPL_URL (page to open); the rest is deploy.sh's.
set -euo pipefail

# shellcheck source=deploy/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/deploy/lib.sh"

readonly URL="${TODOIMPL_URL:-http://127.0.0.1:${APP_PORT}/}"

bash "${REPO_DIR}/scripts/deploy.sh"
echo "run.sh: opening ${URL}"
# Detached and silenced: a freshly launched browser would otherwise hold this terminal and flood it.
setsid -f xdg-open "$URL" </dev/null >/dev/null 2>&1

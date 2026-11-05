#!/bin/bash
# (Re)create the oauth2-proxy container that guards https://agents.kuhy.duckdns.org.
# Host network, bound to 127.0.0.1:4186 only; Google provider; exactly one allowed email;
# secrets from ~/.config/todoImplementer/oauth2-proxy.env (0600, never in git).
#
#   deploy/oauth2-proxy/run.sh             create/replace the container (needs client id+secret)
#   deploy/oauth2-proxy/run.sh --dry-run   print the docker command, start nothing
set -euo pipefail

# shellcheck source=../lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib.sh"

# Newest stable at 2026-11-05 (github.com/oauth2-proxy/oauth2-proxy releases); exact pin.
readonly IMAGE="${OAUTH2_PROXY_IMAGE:-quay.io/oauth2-proxy/oauth2-proxy:v7.15.5}"
readonly NAME=todoimplementer-oauth2-proxy
DRY_RUN=0
case "${1:-}" in
"") ;;
--dry-run) DRY_RUN=1 ;;
*) die "usage: $0 [--dry-run]" ;;
esac
command -v docker >/dev/null || die "docker is required"

deploy_tools ensure-env "$ENV_FILE" >/dev/null
deploy_tools write-emails "$EMAILS_FILE" "$ALLOWED_EMAIL"

docker_cmd=(
	docker run -d --name "$NAME" --restart unless-stopped --network host
	--env-file "$ENV_FILE"
	-v "${EMAILS_FILE}:/etc/oauth2-proxy/emails.txt:ro"
	"$IMAGE"
	--provider=google
	--http-address="127.0.0.1:${PROXY_PORT}"
	--redirect-url="$REDIRECT_URI"
	--authenticated-emails-file=/etc/oauth2-proxy/emails.txt
	--upstream=static://202
	--reverse-proxy=true
	--cookie-secure=true
	--cookie-expire=168h
	--skip-provider-button=true
)

if ((DRY_RUN)); then
	printf 'dry run, would run:'
	printf ' %q' "${docker_cmd[@]}"
	echo
	deploy_tools check-creds "$ENV_FILE" || echo "note: credentials still missing (google_oauth_handoff.sh)"
	exit 0
fi

deploy_tools check-creds "$ENV_FILE"
# Our own container may hold the port; anything else listening is foreign: refuse.
if [[ -z "$(docker ps -aq --filter "name=^${NAME}\$")" ]]; then
	listener="$(listener_on "$PROXY_PORT" || true)"
	[[ -z "$listener" ]] || die "port ${PROXY_PORT} is taken: ${listener}"
fi
docker rm -f "$NAME" >/dev/null 2>&1 || true
"${docker_cmd[@]}"
echo "started ${NAME} on 127.0.0.1:${PROXY_PORT} (${IMAGE})"

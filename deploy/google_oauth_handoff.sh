#!/bin/bash
# Gate-2 handoff for the one step with no API: creating the Google OAuth web client.
# Opens the console page, puts each form field on the clipboard in form order, takes the
# client id/secret into the 0600 env file, then --verify-only proves the proxy redirects
# to Google with the right client id and redirect URI.
#
#   deploy/google_oauth_handoff.sh               guided: open page, clipboard, paste creds
#   deploy/google_oauth_handoff.sh --verify-only check a running proxy (rerunnable)
#   deploy/google_oauth_handoff.sh --public      with --verify-only: check via Caddy
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

readonly CONSOLE_URL="https://console.cloud.google.com/apis/credentials/oauthclient"
VERIFY_ONLY=0
PUBLIC=0
for arg in "$@"; do
	case "$arg" in
	--verify-only) VERIFY_ONLY=1 ;;
	--public) PUBLIC=1 ;;
	*) die "usage: $0 [--verify-only [--public]]" ;;
	esac
done

# to_clipboard <text>: X11 clipboard, Wayland fallback.
to_clipboard() {
	if command -v xclip >/dev/null; then
		printf '%s' "$1" | xclip -selection clipboard
	elif command -v wl-copy >/dev/null; then
		printf '%s' "$1" | wl-copy
	else
		die "need xclip or wl-copy for the clipboard"
	fi
}

# step <label> <value>: copy value, wait for Enter.
step() {
	to_clipboard "$2"
	read -r -p "Copied ${1}. Paste it in the form, then press Enter for the next field... " _
}

verify() {
	local base="http://127.0.0.1:${PROXY_PORT}"
	((PUBLIC)) && base="https://${PUBLIC_HOST}"
	deploy_tools check-creds "$ENV_FILE"
	local client_id
	client_id="$(sed -n 's/^OAUTH2_PROXY_CLIENT_ID=//p' "$ENV_FILE")"
	deploy_tools check-start "${base}/oauth2/start?rd=/" "$client_id" "$REDIRECT_URI" >/dev/null
	echo "verified: ${base}/oauth2/start redirects to accounts.google.com with the right client"
}

if ((VERIFY_ONLY)); then
	verify
	exit 0
fi

deploy_tools ensure-env "$ENV_FILE" >/dev/null
echo "Create a 'Web application' OAuth client (consent screen: External, add ${ALLOWED_EMAIL} as test user)."
xdg-open "$CONSOLE_URL" >/dev/null 2>&1 || echo "open manually: ${CONSOLE_URL}"
step "Name" "todoImplementer"
step "Authorized JavaScript origin" "https://${PUBLIC_HOST}"
step "Authorized redirect URI" "$REDIRECT_URI"
read -r -p "Client ID: " client_id
read -r -s -p "Client secret (hidden): " client_secret
echo
printf '%s' "$client_id" | deploy_tools set-key "$ENV_FILE" OAUTH2_PROXY_CLIENT_ID
printf '%s' "$client_secret" | deploy_tools set-key "$ENV_FILE" OAUTH2_PROXY_CLIENT_SECRET
echo "saved to ${ENV_FILE} (0600). Next: deploy/oauth2-proxy/run.sh, then rerun with --verify-only"

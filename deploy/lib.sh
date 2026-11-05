#!/bin/bash
# Shared helpers for the deploy scripts (source this file; it sets no shell options).
# shellcheck disable=SC2034  # constants are consumed by the scripts that source this

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DEPLOY_DIR
readonly REPO_DIR="${DEPLOY_DIR%/deploy}"
readonly CONFIG_DIR="${TODOIMPL_CONFIG_DIR:-${HOME}/.config/todoImplementer}"
readonly ENV_FILE="${CONFIG_DIR}/oauth2-proxy.env"
readonly EMAILS_FILE="${CONFIG_DIR}/oauth2-proxy-emails.txt"
readonly ALLOWED_EMAIL="krzysztofrudnicki0@gmail.com"
readonly PUBLIC_HOST="agents.kuhy.duckdns.org"
readonly REDIRECT_URI="https://${PUBLIC_HOST}/oauth2/callback"
readonly APP_PORT="${TODOIMPL_APP_PORT:-8786}"
readonly PROXY_PORT="${TODOIMPL_PROXY_PORT:-4186}"
readonly UNIT_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"

die() {
	echo "Error: $*" >&2
	exit 1
}

# deploy_tools <subcommand> [args...]: the Python helper next to this file.
deploy_tools() {
	python3 -I "${DEPLOY_DIR}/deploy_tools.py" "$@"
}

# listener_on <port>: print the ss line of whatever listens on 127.0.0.1/any <port>.
listener_on() {
	ss -ltnpH "sport = :$1"
}

# install_unit <file-name>: copy deploy/<file-name> into the systemd --user unit dir (no reload).
install_unit() {
	install -Dm644 "${DEPLOY_DIR}/$1" "${UNIT_DIR}/$1"
}

#!/bin/bash
# Put the Firebase service-account key the FCM pinger signs with in place
# (DOCS-native-app-relay.md "Notifications"). Creating a key is a console click
# only kuhy can make; everything around it is scripted:
#   1. opens the project's "Service accounts" page, signed in as the account the
#      firebase CLI uses;
#   2. waits for the downloaded *-firebase-adminsdk-*.json in ~/Downloads;
#   3. moves it to ~/.config/todoImplementer/fcm-service-account.json (0600);
#   4. proves it works: Google trades it for an access token (no message sent).
# A failed check prompts to retry. Rerun with --verify-only to check only.
#
# Usage: scripts/fcm_key.sh [--verify-only]
# Needs: firebase CLI (logged in), uv, xdg-open.
set -euo pipefail

readonly PROJECT="${TODOIMPL_FIREBASE_PROJECT:-kuhy-syncs}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
readonly REPO
readonly TARGET="$HOME/.config/todoImplementer/fcm-service-account.json"
readonly DOWNLOADS="${XDG_DOWNLOAD_DIR:-$HOME/Downloads}"
readonly WAIT_S=600

die() {
    echo "error: $1" >&2
    exit 1
}

verify() {
    PYTHONPATH="$REPO/server" uv run --quiet --project "$REPO" python -m todoimpl.relay.fcm_check
}

account() {
    # The console must open as the same Google account the firebase CLI uses.
    timeout 20 firebase login:list 2>/dev/null | sed -n 's/.*Logged in as \([^ ]*\).*/\1/p' | head -1
}

newest_key() {
    find "$DOWNLOADS" -maxdepth 1 -name "${PROJECT}-firebase-adminsdk-*.json" -newer "$1" -printf '%T@ %p\n' \
        2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-
}

fetch() {
    local who stamp found=""
    who="$(account)" || true
    [[ -n "$who" ]] || die "firebase CLI is not logged in (run: firebase login)"
    stamp="$(mktemp)"
    trap 'rm -f "$stamp"' RETURN
    setsid xdg-open \
        "https://console.firebase.google.com/project/${PROJECT}/settings/serviceaccounts/adminsdk?authuser=${who}" \
        >/dev/null 2>&1 &
    echo "Click 'Generate new private key', then 'Generate key'. Waiting for the download..."
    for _ in $(seq "$WAIT_S"); do
        found="$(newest_key "$stamp")"
        [[ -n "$found" ]] && break
        sleep 1
    done
    [[ -n "$found" ]] || die "no ${PROJECT}-firebase-adminsdk-*.json appeared in $DOWNLOADS"
    install -D -m 600 "$found" "$TARGET"
    rm -f "$found"
    echo "key stored in $TARGET"
}

main() {
    if [[ "${1:-}" == "--verify-only" ]]; then
        verify
        return
    fi
    while true; do
        fetch
        if verify; then
            echo "Restart the board to pick it up now: $REPO/scripts/deploy.sh (it also loads on the next ping)."
            return
        fi
        read -r -p "The key did not work. Retry [r] or quit [q]? " answer
        [[ "$answer" == "r" ]] || exit 1
    done
}

main "$@"

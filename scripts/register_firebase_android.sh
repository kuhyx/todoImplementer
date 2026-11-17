#!/bin/bash
# Register the native app in Firebase project kuhy-syncs: one Android app for
# com.kuhy.todo_implementer plus the shared release key's SHA-1. Firebase
# creates the matching Android OAuth client for that (package, SHA-1) pair, so
# Google sign-in works on the phone (build-mobile-app R9). Idempotent: an app
# or SHA that already exists is left alone. Pattern:
# ~/.claude/scripts/lib/phone_slot_firebase.sh.
#
# Usage: scripts/register_firebase_android.sh [--check]
#   --check  exit 0 only if the app and the SHA-1 are both registered.
# Needs: firebase CLI (logged in), jq, keytool.
set -euo pipefail

readonly PROJECT="${TODOIMPL_FIREBASE_PROJECT:-kuhy-syncs}"
readonly PACKAGE="com.kuhy.todo_implementer"
readonly DISPLAY_NAME="todo_implementer"
readonly KEY_PROPS="${TODOIMPL_KEY_PROPS:-$HOME/.android/release/key.properties}"

die() {
    echo "error: $1" >&2
    exit 1
}

fb() {
    local out
    out=$(timeout 50 firebase "$@" --project "$PROJECT" --json 2>/dev/null) ||
        die "firebase $1 failed (logged in? firebase login:list)"
    sed -n '/^{/,$p' <<<"$out"
}

app_id() {
    fb apps:list ANDROID | jq -r --arg p "$PACKAGE" \
        '[.result[]? | select(.packageName == $p) | .appId][0] // empty'
}

release_sha1() {
    local ks alias pw
    [[ -f "$KEY_PROPS" ]] || die "no key.properties at $KEY_PROPS"
    ks=$(sed -n 's/^storeFile=//p' "$KEY_PROPS" | head -1)
    alias=$(sed -n 's/^keyAlias=//p' "$KEY_PROPS" | head -1)
    pw=$(sed -n 's/^storePassword=//p' "$KEY_PROPS" | head -1)
    KS_PASS="$pw" keytool -list -v -keystore "$ks" -alias "$alias" -storepass:env KS_PASS 2>/dev/null |
        sed -n 's/^[[:space:]]*SHA1:[[:space:]]*//p' | head -1 | tr -d ':' | tr 'A-F' 'a-f'
}

sha_registered() {
    fb apps:android:sha:list "$1" | jq -e --arg s "$2" \
        '[.result[]? | .shaHash | ascii_downcase] | index($s)' >/dev/null
}

main() {
    local id sha
    sha=$(release_sha1)
    [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || die "could not read a SHA-1 from the release keystore"
    id=$(app_id)
    if [[ "${1:-}" == "--check" ]]; then
        [[ -n "$id" ]] && sha_registered "$id" "$sha"
        return
    fi
    if [[ -z "$id" ]]; then
        echo "creating Firebase app $PACKAGE"
        fb apps:create ANDROID "$DISPLAY_NAME" --package-name "$PACKAGE" >/dev/null
        id=$(app_id)
        [[ -n "$id" ]] || die "apps:create succeeded but $PACKAGE is not listed"
    fi
    if ! sha_registered "$id" "$sha"; then
        echo "registering release SHA-1 on $PACKAGE"
        fb apps:android:sha:create "$id" "$sha" >/dev/null
    fi
    echo "$PACKAGE registered as $id"
}

main "$@"

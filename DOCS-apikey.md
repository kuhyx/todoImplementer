# Claude API key lifecycle

Why: part of the Max plan is a monthly grant of API credits in a Claude Console org. Turns that run on it (a later
part) need a Console API key, which expires after 30 days and can only be created by hand. This part keeps the key
healthy and makes a problem impossible to miss. Code: `server/todoimpl/apikey/`, `scripts/rotate_api_key.py`.

## Files (mode 0600, never in a log, a transcript or a command line)

`~/.config/todoImplementer/anthropic_api_key` (`$TODOIMPL_APIKEY` moves it) holds the key; `<path>.json` holds
`{"created": "YYYY-MM-DD", "expires": "YYYY-MM-DD"}`. A key "looks like a key" when it matches
`^sk-ant-[A-Za-z0-9_-]{20,}$` (prefixes vary: `api03`, `usr01`...); the live check decides real validity.

## Status

`status()` returns `KeyStatus(state, expires, detail)` plus `usable` (ok or expiring). Order of rules:

| State | When |
|---|---|
| missing | no key file, or it is blank |
| invalid | wrong format, or the API answered 401/403 or an authentication/permission error ("expired or revoked") |
| expired | the recorded expiry is past (no network call) |
| check_failed | network error, timeout, 5xx or any reply that is not a verdict: never shown as fine |
| expiring | valid and 3 days or fewer left (still usable) |
| ok | valid, more than 3 days left (or no expiry recorded) |

The live check is `GET https://api.anthropic.com/v1/models` with `x-api-key` and `anthropic-version: 2023-06-01`: it
costs no tokens. A $0 credit balance (billing error, "credit balance" text) never makes a key invalid.

## Monitor (`apikey/monitor.py`)

Started by `build_backend`: a check off the startup path, then hourly, and at once when a key file changes (so the
board clears right after a rotation). It runs whether or not the key is used and whatever the credit balance is. While
the state is not ok it adds ONE todo task `MANUAL WORK REQUIRED: rotate Claude API key` (repo `kuhyx/todoImplementer`,
priority high; body: state, expiry, the command) and closes it when ok again. It sends ONE `notify-send` per state
change (last state kept in `$TODOIMPL_HOME/apikey-notified.json`, so restarts stay quiet); a missing `notify-send`
is logged. `GET /api/board` carries `api_key` (`state`, `level` ok/warn/error, `text`, `expires`; schema in
`contracts/board.schema.json`); the page shows a red banner (error) or an amber one (warn) with the server's text.

## Rotation (`scripts/rotate_api_key.py [--no-open] [--days 30]`)

Opens the Console keys page, then a hidden prompt `paste the new key (hidden):`. An empty answer watches the
clipboard (xclip, 1 s, up to 10 min) for a new key. The key must match the format, differ from the stored one,
and pass the live check before anything is written; then both files are saved (created today, expires today + days),
the clipboard is cleared and `saved, expires <date>` is printed. A failure asks `retry / skip` and never advances;
a rejected key is not tried twice, a network failure may be retried with the same key.

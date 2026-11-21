# Relay contract: the app <-> the PC worker over Firebase RTDB

How the native app (`DOCS-native-app.md`) talks to the server without HTTP. The transport code is the shared
package `~/src/utils/rtdb_relay/` (API: its `README.md`); this file fixes what todoImplementer puts on it.
Schemas: `contracts/relay-request.schema.json`, `relay-result.schema.json`, `relay-nodes.schema.json`.
The pattern is the tutor's (`~/src/tutor/DOCS-contract.md` sections 3-5 and 12); where this file is silent, the
tutor's rules apply.

## Running it (code: `server/todoimpl/relay/`)

The worker is a thread beside the HTTP server, started by `serve()` only when `TODOIMPL_RELAY=1` (tests never set
it; the systemd unit needs `Environment=TODOIMPL_RELAY=1`). It needs crdt-sync's `~/.config/crdt-sync/firebase.json`,
this app's own Firebase session `~/.config/todoImplementer/firebase_auth.json` (seed it once with crdt-sync's
`python3 -m tool.seed_session --client-id ... --client-secret ... --app todoImplementer`) and the passphrase in
`~/.config/crdt-sync/password`. Missing any of them, it serves nothing, the board banner (`alert` kind `relay`)
names the cause, and it retries after 5 s, 15 s, then every 60 s. Snap nodes are polled: board every 1 s,
sessions 5 s, usage and merges 10 s. The FCM pinger plugs into `Publisher(on_board=...)` and `notify_test`.

Live checks of a slot build (`phone_deploy.sh --slot`, `SYNC_NAMESPACE=sandbox/slotN`) run a scratch server with
`TODOIMPL_RELAY_NAMESPACE=sandbox/slotN` (anything else outside `sandbox/<lowercase>` is refused): every path, the
key header included, lives under that namespace, and the AAD stays the plain layout root, as the app's. Without
it the worker unlocked with the production header (rtdb_relay's `unlock` reads through `rtdb.at("")`) and dropped
every slot request as undecryptable (T2354). The e2e world's server env points `TODOIMPL_TODO_NOTE` at a recording
shim, so a repo-less task never reaches the real todo app (T2355).

## Layout (root `todoimpl/v1-e2e`)

| Node | Writer | Content |
|---|---|---|
| `meta` (clear) | worker | `{min_client, schema: 1}` |
| `e2e` (clear) | worker, once | the sealing header (salt, cost, check MAC), as the tutor's `tutor/e2e` |
| `rev` (clear) | worker | `{board, usage, sessions, merges}` counters, bumped after the matching `snap` node is written |
| `snap/board` | worker | exactly the `GET /api/board` body |
| `snap/usage` | worker | exactly the `GET /api/usage` body |
| `snap/sessions` | worker | exactly the `GET /api/sessions` body |
| `snap/merges` | worker | exactly the `GET /api/merges` body |
| `presence/workers/{dev}` | worker | heartbeat every 30 s, with `version` and `build` (replaces `GET /version`) |
| `presence/clients/{dev}` | app | platform, app version, build number, `seen`, FCM token or null |
| `watch/{dev}` | worker | which card's live feed is mirrored for that client, and until when |
| `live/{card}/{seq}` | worker | the `/api/live` events of a watched card, key `s` + 9-digit seq continuing above the highest stored key (restarts too), last 200 kept; a new mirror skips activity already there (T2345) and writes one PATCH per second (T2346) |
| `requests/{rid}/req` | app | a request (`relay-request.schema.json`) |
| `requests/{rid}/claim` (clear) | worker | lease, attempt and phase, as the tutor |
| `requests/{rid}/result` | worker | the answer (`relay-result.schema.json`) |

Publishing: the worker writes a `snap` node when its JSON changes, at most every 250 ms per node, then bumps
`rev`. The app streams `rev`, `presence/workers` and, while a drawer is open, `live/{card}`; it GETs a `snap` node
when its counter moves. The app keeps each card's last feed (in memory, the newest 50 events in its preferences on
close) and shows it at once on the next open (T2353). A `snapshot_refresh` request republishes every node (pull to refresh, first start).

## Sealing

Every unit is `{"_e2e": <blob>, <clear keys>}`: crdt-sync's `E2eCipher` (XChaCha20-Poly1305) over the unit's
JSON, key = Argon2id of the shared crdt-sync password, AAD = the unit's full path. A blob cannot be moved to
another path or rid. Clear: `meta`, `e2e`, `rev`, `requests/*/claim`, `created` in `req`, `at` in `result`,
`beat` in worker presence, `seen` in client presence. Units: everything else. Unlike the tutor, **no legacy
plaintext unit is accepted anywhere**: this root never had one. RTDB stores no empty object, so a `req` whose `body`
(or `args`) was `{}` arrives without it, and `live_watch` `{card: null}` arrives as `{}`; the worker reads
the missing key as `{}` (as `null` for that card, and for the `mark` of a `session_mark`, an unmark). For the same reason a result or snap node arrives without its
`null` values and empty lists and objects; the app reads a missing key as that empty value.

## Kinds

Write kinds (lane `act`, one at a time, in key order). Every POST route has one, except `POST /api/pair`, which
belongs to the browser device gate and goes away with it.

| Kind | HTTP route | Body |
|---|---|---|
| `task_start` ... `task_done_manually` (12) | `POST /api/task/<card>/<action>`, action in `bodies.ACTIONS` | `{card, args}`; args = `requests.schema.json#/$defs/<action>` |
| `ask_answer` ... `ask_reject` (6) | `POST /api/task/<card>/ask/<verb>` | `{card, args}`; args = `requests.schema.json#/$defs/ask_<verb>` |
| `new_task` | `POST /api/new-task` | `{args}`; args = `$defs/new_task` (body cap stays `newtask.MAX_BODY`) |

`task_send` also gets `newtask.MAX_BODY` (40 MB), since its `images` may carry inline bytes ("Images" below).
| `credits_fallback` | `POST /api/settings/credits-fallback` | `{args}`; args = `$defs/credits_fallback` |
| `merge_merge`, `merge_dismiss` | `POST /api/merge/<group>/<merge or dismiss>` | `{group, args: {}}` |
| `session_resume`, `session_mark`, `session_delete`, `session_handoff` | `POST /api/sessions/<verb>` | `{args}`; args = `sessions.schema.json#/$defs/<verb>_body` |

The twelve task actions: `start`, `spec-answers`, `spec-ok`, `send`, `ship`, `close`, `cancel`, `lesson-approve`,
`go`, `rerun`, `wont`, `done-manually` (kind = `task_` + the action with `-` turned to `_`). `new_task` then starts the card, as the route does.
Since T2060 no card offers `ship` or `close` (a green card ships itself), so those two kinds answer `disabled`.

Read kinds (lane `read`, up to 4 at once). The GET routes that a `snap` node does not cover:

| Kind | HTTP route | Body | Result `data` |
|---|---|---|---|
| `task_detail` | `GET /api/task/<card>` | `{card}` | `task.schema.json` |
| `task_issues` | `GET /api/task/<card>/issues` | `{card}` | the route's body |
| `task_shot` | `GET /api/task/<card>/shot/<name>` | `{card, name}` | `{png_b64}`, at most 4 MB of PNG |
| `umbrella`, `umbrella_log` | `GET /api/umbrella/<card>[/log/<log>]` | `{card}`, `{card, log}` | `umbrella.schema.json` |
| `tokens` | `GET /api/tokens[<path>]?<query>` | `{path, query}` | the tokens router's body |
| `live_watch` | `GET /api/live?id=<card>` (SSE) | `{card}` or `{card: null}` | `{}`; the feed lands in `live/{card}` |
| `image_upload` | none (stages like `POST /api/upload`) | `{data_b64}` | `{upload: {id, name, size}}`; 40 MB req cap |
| `snapshot_refresh` | `GET /api/board`, `/api/usage`, `/api/sessions`, `/api/merges` | `{}` | `{}`; nodes republished |
| `notify_test` | none | `{}` | `{}`; sends one ping to the asking device |

`GET /version` is covered by `presence/workers/{dev}`; static files are not needed (the app bundles its UI).

A watch lasts 120 s; the app renews it every 60 s while the drawer is open and sends `{card: null}` on close.

## Images (`[Image #N]`, T2320-T2322)

Send to Claude and New task take numbered images through one shape: `images` = `requests.schema.json#/$defs/image_refs`,
any number of `image_ref` items (1000 as a sanity bound; the bytes are capped, `uploads.MAX_TASK`; kuhy 2026-11-21,
T2426), item N being `[Image #N]` in the text. An item is `{upload: <id>}` or `{data_b64}` (inline bytes, 6 MB
decoded). The page posts `/api/upload` first; the app sends each image alone as the relay kind `image_upload`
`{data_b64}` (answered by the worker: staged like `/api/upload`, result `{upload: {id, name, size}}`), then
`task_send` / `new_task` with `{upload: <id>}` items. A refused upload stops the send; a retry sends only the
images that did not go up. The server reads the type
from the first bytes (png, jpeg, webp, gif) and refuses anything else with the item's number
(`newtask/noteimages.py`). Send copies each image to `<run>/inbox/<ms>-<N>.<ext>` and appends to the note
`(runner) kuhy attached images; open each with the Read tool:` plus one `[Image #N] = <absolute path>` line each; the
run dir is a turn `--add-dir`. Turns are `claude -p <text>`, so the images reach the session as paths for its Read
tool, not as image blocks. A refused send keeps the staged uploads, so a retry sends the same ids. New task writes
image N as `<n>.<ext>` in the dufs folder under a `[Image #N]` line above its `![](…)` link; the prompt turns the
link into the local path.
The app (T2330-T2336) offers gallery, camera and keyboard paste in both note boxes and the New task details as `#N`
chips; the phone re-encodes picks to 1600 px JPEG, and `image_attach.dart` shrinks anything else to fit. Because the
relay seals each `req` into one RTDB string (10 MB cap, about 16/9 of the bytes after two base64 passes), one image
may be 4.5 MB; there is no count cap; a refusal shows as a red glyph.

## Results and errors

A result is `{ok: true, at, kind, data}`; `data` is the JSON body the HTTP route answers with on 200, without its
`ok` key (a PNG is `{png_b64}`, a text body `{text}`). A refusal is `{ok: false, at, kind, code, error, retry}`. The HTTP codes keep their meaning (`disabled` carries the action's
reason). Relay-only codes: `unknown_kind`, `unsealed`, `expired`, `rate_limited`, `too_large`, `stale_client`,
`gave_up`. The app draws each code as a glyph (textgate); `error` is for the log and the copy-errors action.

## Guards (done criteria D5)

The relay is a second way to start Claude sessions that push code, so it gets its own guards. Each one has a test
that fails without it.

1. **Allowlist.** A `kind` outside `relay-request.schema.json#/$defs/kind` gets `unknown_kind`; no backend method
   runs. The dispatcher is a table keyed by kind; there is no `getattr` on a name from the request.
2. **Schema first.** The whole opened `req` is validated against `relay-request.schema.json` (which pins each
   kind's args to the HTTP body schema) before dispatch. Failing: `bad_request`, nothing runs.
3. **Sealed only.** A `req` without `_e2e`, or whose blob does not open with the key and its own path as AAD, gets
   `unsealed` (written sealed) and is never dispatched. No plaintext fallback.
4. **Same rules as a click.** Write kinds go through the same dispatcher as the HTTP routes: the card must offer the
   action and it must be enabled, an `auto_ship` option (if offered) must be enabled, ids must match `CARD_ID`, shot names `SHOT_NAME`.
   A test runs every kind through both transports against one fake backend and compares the replies.
5. **Once per rid.** The done-log answers a replayed rid from its record; `sent_at` older than 24 h is `expired`.
6. **Rate cap.** More than 30 write requests in a minute: `rate_limited` until the minute passes.
7. **Size caps.** `req` over 256 KB (over `newtask.MAX_BODY` for `new_task` and `task_send`) is `bad_request`; results over 4 MB are
   `too_large`.
8. **Fail closed.** No password, wrong password or no Firebase session: the worker writes nothing and serves no
   request; the HTTP board keeps working; the board's `alert` names the cause.

Caveat: the RTDB rules give the whole database to one Google uid, not to this app. Any of kuhy's crdt-sync apps
holding that uid's refresh token can write under `todoimpl/`. Only a holder of the crdt-sync password can write a
request that opens, so the password is the gate; it lives in `~/.config/crdt-sync/password` (0600) and the phone's
keystore, never in a repo.

## Notifications (FCM)

1. The worker keeps the last board snapshot it published. After each publish it compares cards: a card that newly
   has column `needs_you` with `needs.category` other than `auto`, and a card whose `needs.kind` newly is `run_failed` or `checks_failed`.
2. Any such change sends one data-only FCM message (HTTP v1 API) to every `presence/clients/*` entry with a non-null
   `fcm` token, coalesced over 2 s. Payload: `relay-nodes.schema.json#/$defs/ping`, counts only, no titles, no ids.
3. The app shows one notification on channel `attention_v1` (ids are versioned; a change means a new id): the app
   glyph and the counts as badges, no text. Tapping opens the board on the Needs you column.
4. Credential: the Firebase service-account key at `~/.config/todoImplementer/fcm-service-account.json` (0600),
   never in the repo. A missing or failing key shows as the board `alert`, never as silence: kind `relay`, text
   `Phone notifications are off: <cause>` (`relay/status.py` NOTIFY, after the relay's own cause). Put the key
   in place with `scripts/fcm_key.sh` (opens the console page, waits for the download, moves it, checks it);
   `scripts/fcm_key.sh --verify-only` or `python -m todoimpl.relay.fcm_check` only checks that Google issues a
   token for it. The key is read again on each token fetch, so a new key needs no restart.
5. Budget: change on the PC to notification on the phone, 10 s at p90 (D4).
6. Code: `relay/pinger.py` (which changes ping, coalescing, `notify_test`), `relay/fcm.py` (RS256 assertion with
   `cryptography`, cached access token, data-only HTTP v1 send). `notify_test` answers `not_found` when the
   asking device has no token or FCM no longer knows it, `disabled` without a usable key, and
   `upstream_unavailable` (retry) when FCM refuses. A token FCM reports as gone is skipped, not an alert.

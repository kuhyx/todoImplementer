# Native Flutter app

The board, the sessions page and the usage page become one Flutter app. It runs on kuhy's phone (Android) and on
the PC (Flutter web in a Chrome `--app` window). It reaches the PC through a Firebase RTDB relay, the way the tutor
app does, so it works over mobile data with no VPN and no QR scan. The wire contract is
`DOCS-native-app-relay.md`; the schemas are `contracts/relay-*.schema.json`.

Decided by kuhy on 2026-11-16 (grilling rounds Q1-Q12, then `override` on the recommended answers).

## Why

The Astro page works on the phone only through the public endpoint `agents.kuhy.duckdns.org` and a paired browser
cookie (`DOCS-phone.md`). kuhy wants a real app: launcher icon, no browser bar, no pairing, notifications when a card
needs him. One Flutter codebase on both screens also ends the duplicate UI once Astro is retired.

## Decisions

| Topic | Decision |
|---|---|
| Scope | Full rewrite of all three pages: board `/` (cards, drawer, asks, umbrella view, merges, new task, credits strip), `/sessions`, `/usage` (token panels) |
| Platforms | Android `com.kuhy.todo_implementer` on the Pixel 6a, and Flutter web on the PC in a Chrome `--app` window |
| Transport | Firebase RTDB relay, root `todoimpl/v1-e2e`, Google sign-in, one uid, E2E sealed with the shared crdt-sync password |
| Relay code | The shared package `~/src/utils/rtdb_relay/` (Python worker half, Dart client half), extracted from the tutor. Its API: `~/src/utils/rtdb_relay/README.md`. This repo only adds the todoImplementer kinds and nodes |
| Server deps | Runtime gains exact-pinned `httpx`, `crdt-sync` and `rtdb_relay` (was stdlib only) |
| Notifications | v1. FCM data-only ping from the PC; events: a card enters Needs you, a run fails (a ready card ships itself, so it pings nothing). Icon + count, no text |
| Icon | Shared family (skill `app-icon`): charcoal field, `#B8862E` glyph of a card with a check and a play arrow |
| Repo | Public (kuhyx/todoImplementer); release APK built and signed by CI on every push |
| CI Firebase secret | `TODOIMPL_FIREBASE_JSON` must carry `webClientId` (plus apiKey, databaseUrl, uid): CI has no `~/src/todo` fallback, and an empty id fails the release job |
| Retirement | Astro `web/` and `agents.kuhy.duckdns.org` stay until every flow in this file's done list passes on the phone with Wi-Fi off; then both go |

## Done criteria

Each item names the check that proves it. All run against the live server and the real phone unless marked.

- [ ] D1. With Wi-Fi off (`adb shell svc wifi disable`), the phone app shows the board, the sessions page and the
      usage page with live data. Proof: screenshots from the app's virtual display plus a new `rev/board` read.
- [ ] D2. Starting a card and shipping a card work from the phone with Wi-Fi off. Proof: the card's status moves
      on the board snapshot and in `state.json`; the ship lands its commit (the same proof as flow F5).
- [ ] D3. An action's result is visible in the app within 2 s at p90 over the relay (20 runs, timestamps from
      the app log and the worker's done-log, phone and PC clocks corrected by `skew_ms`).
- [ ] D4. A card that enters Needs you (not category `auto`) raises a notification on the phone within 10 s, with
      the app closed. Proof: the worker's ping log line and `adb shell dumpsys notification` within the window.
- [ ] D5. Every security guard in `DOCS-native-app-relay.md` ("Guards") has a test that is red without the guard.
- [ ] D6. Every page works in the PC window as well (Flutter web, same relay), checked headlessly on a second
      instance, never on kuhy's display.
- [ ] D7. Each of the five core flows of `DOCS-features.md` (F1-F5) passes through the app, not the Astro page.
- [ ] D8. Only then: `web/`, the device gate (`device_gate.py`, `pairing.py`, `devices_store.py`) and the Caddy site
      for `agents.kuhy.duckdns.org` are removed, with kuhy's OK on the Caddy change (CLAUDE.md "Ask first").

## Structure

```
app/                      Flutter project (pattern: ~/src/tutor/app)
  lib/main.dart           entry: platform seam, sign-in gate, unlock gate, shell
  lib/relay/              todoImplementer kinds on top of rtdb_relay (requests, results, error glyphs)
  lib/model/              Dart types generated from or tested against contracts/*.schema.json
  lib/board/ sessions/ usage/   one folder per page; widgets <= 250 lines per file
  lib/notify/             FCM receive, channel attention_v1, badge drawing
  test/                   widget + unit tests; contract tests read ../contracts and tests/fixtures
  android/                applicationId com.kuhy.todo_implementer, INTERNET in the main manifest
server/todoimpl/relay/    worker: kinds -> one dispatcher shared with the HTTP routes, snapshot publisher, pinger
contracts/relay-*.schema.json   request, result, nodes (incl. the FCM ping)
```

Board page details (kuhy, 2026-11-20): the strip shows two rings beside the credits switch, the fuller plan window
(5 h or 7 d, from `snap/usage`) and the week's credit spend against `cap_usd` (red at the limit, dim when off); a tap
lists the numbers and resets (T2348). Add task is a full-screen page: a repo chooser (none = one repo-less note triage
routes, all = one task per board repo, some = one per picked repo) that folds once picked, one text box whose first
line is the title, and the image buttons, images and send in one row (T2349-T2352).

The server keeps one dispatcher for both transports. The HTTP routes and the relay worker call the same function
for every action, so the server-computed rules (an action runs only when the card offers it enabled) hold for both.

## Tests

- Server: pytest at 100 % line and branch as today. The relay worker runs against a fake RTDB (no network) and,
  in the e2e step, a local RTDB emulator. Never the production database.
- Differential: every write kind goes through the HTTP route and through the relay against the same fake backend;
  the replies must match (skill `property-and-differential-tests`).
- App: `very_good_analysis`, 100 % coverage, widget tests with a fake relay. The Pixel 6a inset test of skill
  `build-mobile-app` R7 on every page (physical size 1080x2400, ratio 2.625, padding top 132 / bottom 63, keyboard
  variant), every page fits one screen with no vertical scroll except list-shaped ones.
- Device: emulator first (`~/.claude/scripts/emulator_run.sh`), then the Pixel through `phone_deploy.sh` with a
  `--release` build. The Wi-Fi-off check of D1 is the gate.

## Implementation parts

Each part is one session or one subagent; later parts read this file and the relay doc only.

| Part | Content | Depends on |
|---|---|---|
| P1 | `rtdb_relay` package in utils, tutor switched to it, wire format unchanged | none (in progress) |
| P2 | Server relay worker: dispatcher refactor, kinds, guards, snapshot publisher, presence, live mirror | P1, this spec |
| P3 | App scaffold: package, icon, focus-owner whitelist, OAuth client for (package, SHA-1), CI release APK, sign-in + unlock | P1 |
| P4 | Board page: columns, cards, drawer, asks, spec answers, send, umbrella view, merges, new task, credits strip | P2, P3 |
| P5 | Sessions page and usage page (token panels) | P2, P3 |
| P6 | FCM: Firebase sender credential, pinger, app receiver, channel, badge | P2, P3 |
| P7 | Desktop: Flutter web build served by the server, Chrome `--app` launcher, then retirement (D8) | P4, P5 |

## Open items

- FCM HTTP v1 needs an OAuth token signed with the service account key (RS256). If `crdt-sync` does not already
  bring a signing library, P6 adds one; that is a new dependency and needs kuhy's OK first.
- The RTDB rules allow the whole tree to the one uid; any crdt-sync app of kuhy's with a token can write requests.
  The E2E key is the real gate for writes (`DOCS-native-app-relay.md`, "Guards").

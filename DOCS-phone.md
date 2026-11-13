# Phone access over mobile data

The board is reachable at `https://agents.kuhy.duckdns.org` without a VPN. Only a phone that scanned a pairing QR
on the PC can use it. This file is the record of how that gate works. Code: `server/todoimpl/http/device_gate.py`,
`pairing.py`, `devices_store.py`; contract `contracts/pair.schema.json`; tests `tests/http/test_http_device_gate.py`,
`test_http_pairing.py`, `test_devices_store.py`, `test_pairing_codes.py`.

## What is public

Caddy (container `gitea-caddy`, host network, :443) runs `reverse_proxy 127.0.0.1:8786`. The server still binds
loopback only and still refuses any other host (`app.py`, `make_server`). A request that Caddy forwards is public.
Everything is refused with 401 until the request carries a paired-device cookie: every page, `/api/*`, `/version`,
the live SSE stream and every POST.

Why a gate in the app: Google sign-in needs an OAuth client that does not exist (`DOCS-spec.md`, Q12/Q15). The board
can start Claude sessions that push code, so an open public port would be remote code execution. kuhy's standing rule
allows a password or device-trust gate instead. Caddy rate limits stay a good idea on top.

## Local or public: the Host header

A request is local only when its `Host` header, lower-cased, is exactly `127.0.0.1:<port>`, `localhost:<port>` or
`[::1]:<port>` for the port the server is bound to. Anything else is public: a missing Host, two Host headers,
`agents.kuhy.duckdns.org`, `evil.com`, `127.0.0.1` with no port, an absolute-form request target.

Why not the peer address: every request arrives from 127.0.0.1, Caddy's too. `X-Forwarded-For`, `X-Real-IP`,
`Forwarded` and the like are written by whoever sends the request, so the gate never reads them. Caddy passes the
visitor's Host through, so the Host is the one signal that tells the PC browser from the internet. It also stops DNS
rebinding: a page on `evil.com` that resolves to 127.0.0.1 still sends `Host: evil.com`, which is public and needs
the cookie.

Local requests behave exactly as before: no cookie, same Origin and CSRF checks on POST.

Caddy side: the site block must be exactly `agents.kuhy.duckdns.org` (no catch-all that proxies other Hosts to
:8786), or a client could send `Host: 127.0.0.1:8786` through it and look local. Optional belt and braces:
`header_up Host agents.kuhy.duckdns.org` inside `reverse_proxy`.

## Pairing flow

1. On the PC (local page) the "pair a phone" button calls `POST /api/pair` (Origin + CSRF as for any POST).
   The reply is `{"url": "https://agents.kuhy.duckdns.org/pair?c=<code>", "expires_at": <epoch s>}` and the page
   draws the URL as a QR.
2. The code is `secrets.token_urlsafe(16)`, valid 300 s, single use, kept in server memory (a restart drops pending
   codes). At most 5 are pending; minting a sixth drops the oldest.
3. The phone scans and opens `GET /pair?c=<code>`. A good code is spent, a device token
   (`secrets.token_urlsafe(32)`) is minted, its SHA-256 goes into the store, and the answer is `303` to `/` with the
   cookie. A bad, expired, reused or missing code is `403` with an empty body. Codes are compared with
   `hmac.compare_digest`.

`POST /api/pair` is local only: a public request gets 403 with or without a cookie, so a stolen phone cannot pair
more phones. `GET /pair` itself works from either side.

## The cookie

`todoimpl_device=<token>; Max-Age=34560000; Path=/; Secure; HttpOnly; SameSite=Lax`

- 34560000 s is 400 days, the most Chrome keeps a cookie.
- Every public HTML page load (`/`, `/usage`, `/sessions`) re-sends the same cookie with a full Max-Age (sliding
  renewal), so a phone in use never expires. Local pages and API calls do not renew.
- `HttpOnly` keeps page scripts away from it; `Secure` needs the https origin; `Lax` plus the Origin and CSRF checks
  on POST cover cross-site requests.

## The device store

`~/.config/todoImplementer/devices.json` (`$TODOIMPL_DEVICES` overrides; every test sets it to a temp file), mode
0600, written to a temp file and renamed (`atomic.write_text`). A JSON list; one entry per phone:

`{"sha256": <hex of the token>, "created": <epoch s>, "last_seen": <epoch s>, "ua": <first 80 chars of User-Agent>}`

- The raw token is never stored; a leaked file does not log anyone in.
- The file is read on every public request and every entry is compared (`hmac.compare_digest`), so changes apply at
  once.
- `last_seen` moves at most once an hour per device, so a page load is not a disk write.
- A missing, unreadable or malformed file means nobody is paired (fails closed). Pairing a new phone rewrites it.
- **Revoke every phone: delete the file.** To drop one phone, remove its entry (match `ua`, `created`).
- An SSE stream that is already open when the file is deleted runs until it ends; new requests are refused.

## Public exemptions (no cookie)

`GET /pair`, `GET /manifest.webmanifest`, `GET /icons/<image>`, `GET /favicon.svg`. Nothing else.

Why: Android mints the installable app (WebAPK) from Google's servers, and they fetch the manifest and icons without
the cookie. `/pair` has to work before the phone has a cookie. They hold no board data. `<image>` is a flat
name (letters, digits, `.`, `_`, `-`, no leading dot) ending in png, webp, svg, ico, jpg or jpeg: `/icons/../index.html` and `/icons/%2e%2e/...` are not exempt, so the
exemption cannot be walked out of. The exemptions are GET only.

## The local flag for the page

A page served to a local request gets `<meta name="todoimpl-local" content="1">` next to the CSRF meta
(`static.py`). A public request never gets it, and any `todoimpl-local` tag a built page ships is removed from the
public copy. The web side shows the "pair a phone" button only when it is present. HTML is `no-store`, so local and
public copies are never mixed in a cache.

## Publishing

`~/src/testsAndMisc/linux_configuration/features/publish_caddy_site.sh agents 8786` writes the plain block
(`agents.kuhy.duckdns.org { reverse_proxy 127.0.0.1:8786 { flush_interval -1 } }`) into
`~/services/gitea/sites/` and reloads Caddy. Publish only after the gated server is live: check
`curl -H 'Host: agents.kuhy.duckdns.org' http://127.0.0.1:8786/api/board` gives 401 first.
`deploy/caddy/agents.kuhy.duckdns.org.caddy` and `deploy/oauth2-proxy/` are the Google sign-in variant, kept for
when an OAuth client exists; they are not live.

## Web side

- Pair a phone: on the PC the server stamps `<meta name="todoimpl-local" content="1">`; the header then shows a QR icon
  (all three pages). Tap -> POST /api/pair (CSRF header) -> modal with the QR of the one-time link, a countdown ring
  and seconds left; a new code is minted when it expires; Esc, backdrop or X closes. Errors show a warning glyph
  (title = the error, tap retries). No words in the UI (textgate). QR: uqr 0.1.3, drawn as one SVG path.
- Install: web/public/manifest.webmanifest + flat icons web/public/icons/{icon-192,icon-512,icon-maskable-512}.png,
  regenerated from favicon.svg by `pnpm --dir web icons` (rsvg-convert). No service worker on purpose: the page
  reloads itself when /version changes and a caching worker would serve stale builds.
- The install icon appears on beforeinstallprompt and hides on appinstalled or when display-mode is standalone.
- Phone layout: safe-area insets on headers, drawer, new-task sheet, toasts; every tap target >= 44 px on coarse
  pointers; checked at 390x844 on /, /usage, /sessions (and with a card drawer open): no horizontal overflow.
- Dev: `pnpm --dir web mock` serves all three pages with fake data, the local meta and POST /api/pair;
  `astro dev` proxies /api and /version with changeOrigin so the device gate sees the loopback host.

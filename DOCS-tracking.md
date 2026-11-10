# Tracking an umbrella run and the free-token strip

kuhy asked (2026-11-10) for a view of an umbrella run that shows progress, the state of each task and its
problems, and how many free tokens are left. Both are text-free (icons and numbers; words only in `title` and
`aria-label`, textgate). Resilience of the run itself: `DOCS-resilience.md`.

## The tracking view

Route: `#umbrella=<card id>` on the board page (`web/src/track/`), opened by the icon link on an umbrella card
and in its drawer; the back icon returns to the board. Works at 390x844 (one column) and 3840x2160 (a grid).
Data: `GET /api/umbrella/<card id>` (`contracts/track.schema.json`, `umbrella/track.py`, `service/tracking.py`),
refetched on every event of the existing SSE `GET /api/live?id=<card id>` and on a 5 s poll as fallback; a
failed fetch keeps the last data marked stale. 404 until the umbrella has a run.

| Part | Content |
|---|---|
| Progress | Segments per child coloured done / ready / running / queued / failed, the same buckets as the card, and `needs` (children that need kuhy). |
| Resting | `resting {kind, until}`: why the run waits by itself, with a countdown: `limit` (plan usage), `network`, `gateway`, `killed`, `crash`, `todo`, `turn` (`state.extra.retry_kind`, `DOCS-resilience.md`). |
| Round | The round in progress with its step (`manager`: worktrees, manager and free workers; `checks`; `verdict`) and the history: per round the width, the width that followed (doubled or not), start and end, and each child as `clean` / `fixed` / `escalate` plus whether it counted (`ok`). |
| Children | Per child: status icon, repo, stage, elapsed time, issue count, the newest issue (phase, model, symptom) on hover and in an expandable row, resting reason, free-worker attempts and how many were killed, links to the worker log (`GET /api/umbrella/<id>/log/<child id>`, the last 64 KB of the newest `worker-<round>.log`) and to the live feed (the umbrella's drawer: child events arrive there prefixed with the repo). |
| Issues | `free-issues.jsonl` grouped by phase and model: count, fixed, the newest 20 raw lines per group; the raw file stays at `GET /api/task/<id>/issues`. |
| ETA | `ceil(children left / width) x median time a finished child took` (start to gate or done, from the child's `started_at` and last save). `width` is the next round's width or the number of running children, whichever is larger. `null` until one child has finished. A rough bound, not a promise: later rounds double when the free tier is clean, and the tail (live check, checks, gate) is inside the child time. |

Server-computed only: the child status is the one `status.compute` gives; the page sorts and computes nothing.
Elapsed time of a child stops at its last save once it rests (gate, shipped, failed, cancelled). A child
that has no state yet has `elapsed: null`. Round `started` and `ended` are written by the runner from this
change on (older rounds show no duration).

## Free tokens: what the gateway tells and what it does not

Source: the OmniRoute gateway (`docker` container `omniroute`, `127.0.0.1:20128`, `$TODOIMPL_FREE_GATEWAY`),
read by `gateway/monitor.py` on its own thread every 30 s (each call under a 2 s timeout, one login). `/api/usage`
carries the newest reading as `free` (`contracts/free.schema.json`): no request ever waits on the gateway.
`free.state`: `ok`, `stale` (last good reading older than 90 s), `down` (the newest read got nothing, figures are
the last good ones), `unknown` (not read yet). The strip sits beside the 5 h / 7 d meters.

Two auth tiers (both read from `~/.config/omniroute/`, never logged or sent to the page):
the API key `api_key` for `/api/v1/models/health` (models that are cooling), and the dashboard session from
`admin_password` via `/api/auth/login` for `/api/providers`, `/api/combos`, `/api/combos/metrics`,
`/api/usage/analytics?period=day`, `/api/usage/call-logs` and `/api/usage/<connection id>`.

What it can show, and from where:

- **Provider state** (`/api/providers`): `ok`, `cooling` (a `rateLimitedUntil` or per-key `cooldownUntil` in the
  future, with the end), `failing` (`testStatus` is not active), `off` (`isActive` false); `backoffLevel` as
  failures. Only whitelisted fields leave the server; the connection record also holds a masked API key and
  account ids and none of it is forwarded.
- **Remaining quota, where a provider reports one** (`/api/usage/<connection id>`): as of 2026-11-10 only OpenRouter
  answers with `quotas` (`free_daily` 50 requests per day, `free_rpm`). Cloudflare answers with an error
  message, AgentRouter wants a console key, and the other 17 connections answer HTTP 400. A quota counts only
  with a `total` above zero and not `unlimited`. The monitor asks every connection once, then only the ones that
  answered, and scans all again every 30 reads. So the strip shows remaining requests for OpenRouter and for any
  provider that starts reporting.
- **Tokens today** (`/api/usage/analytics`, today's UTC `dailyTrend` entry): prompt and completion tokens and
  requests of **every client of the gateway** (all offload tools share one `local-tools` key).
- **Tokens by our runs**: the sum of tokens of the newest 300 gateway calls (`/api/usage/call-logs`) whose time
  falls inside the start/end of one of our free-worker attempts today (`free-workers.jsonl`, a 2 s margin).
  Best effort: a worker running long after the newest 300 calls misses its early calls, and another client
  calling at the same moment is counted. `null` when no worker ran today.
- **Chain health** (`/api/combos` + `/api/combos/metrics`): the `free-best` combo's steps in order, each with its
  provider's state, request count, success rate and last use; the combo's success and fallback rates.
- **Models cooling** (`/api/v1/models/health`): how many of the ~360 models are paused.

What it cannot show, and why: **a remaining token or request budget for providers other than the few that
report a quota.** The gateway itself says so in its telemetry rules: no quota source means `unknown`, never
"exhausted"; for key-based free providers there is no provider API for it. For them the strip shows usage
(tokens, requests), cooldown and test state instead. `quota_known` in `counts` says how many providers have a
real number. The `credits` quota of OpenRouter (total 0) is not a budget and is dropped.

Tooltips (not visible text) carry the provider, label, `used/total` and the reset time.

## Defaults chosen (not in the brief)

- The tracking route is a hash route on the board page, not a new page.
- `free` rides on `/api/usage`, which the strip already polls every 10 s; no new endpoint for it.
- The poll cadence is 30 s: every gateway call measured 3 to 240 ms on 2026-11-10 (the OpenRouter quota call is
  the slowest, 0.2 s).
- Worker logs are served as the last 64 KB, plain text, never cached.
- A child's live feed link opens the umbrella drawer: child runs are not board cards and have no SSE of their own.

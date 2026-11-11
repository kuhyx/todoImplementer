# Free API credits, routes and the overage guard

kuhy pays for the Max subscription and nothing else. The plan includes a monthly grant of API credits in a Console org
(no payment method, $0 purchased). Anthropic covers the Claude Agent SDK with it and does not cover the `claude`
CLI, so credit turns go through the SDK; the CLI is never run with the key and no SDK identity is spoofed.
Key lifecycle: `DOCS-apikey.md`. Code: `server/todoimpl/credits/`, `runner/credit.py`, `sdkturn.py`, `guard.py`.

## Routes

A turn takes one route, chosen when it actually starts (`credits.route.choose`): credits while the fallback is `ready`
and the weekly pace has room (below); otherwise the plan, or, when the plan is limited too (`limit-until`), a wait
(`paused_limit`). Any role continues on either route turn by turn: the session id, the cost and the run state are
shared, so a plan session resumes on credits and back. `state.extra.route`, `sessions[role].route`, the
`<stem>.route` file and `<stem>.result.json` record the route; the card shows a "free credits" badge and the feed
a line at each turn start.

Fallback is `ready` only when all hold: the global setting is on (default on; `~/.config/todoImplementer/
settings.json`, `$TODOIMPL_SETTINGS`; toggled on the board through `POST /api/settings/credits-fallback`
`{enabled}`, Origin + CSRF like every POST), the SDK venv exists, the key is usable (the monitor's cached status,
never a network call in a request or the queue) and the credits are not exhausted. The server words the state
(`off`, `ready`, `exhausted`, `unavailable`) in `limit.credits`; the page only shows it.

## Pacing: the grant is spread over the period, the cap is hard

The grant is about $200 a month (the promotional grant of 2026-11-10 lasts to 2026-12-13). Settings in
`settings.json`, edited in the file (no endpoint): `credits_monthly_usd` (default 190: the $200 grant minus a $10
margin, because billing lags and week 4 must never push the balance negative again), `credits_month_start_day`
(default 10, 1 to 28: the period starts on the grant day at 00:00 local and lasts to the next), `credits_cost_factor`
(default 1.0). Week = `min(4, days since the period start // 7 + 1)`; cap = `week x monthly / 4` (days 22 on are
week 4 = the whole grant). A new turn takes the credits only while `spent + 2 x running credit turns < cap`;
past that it takes the plan, and if the plan is limited it waits for the limit: the cap is never spent past, not
even as a limit fallback. Turns already running finish on their route. The old `credits_first` setting is gone:
pacing is always on (the key in an old file is ignored). A real billing error still marks the credits exhausted
(below), and the mark is kept to its end even with no plan limit, so no credit retry follows every dispatch.

The cost is an estimate of the Console bill. The ledger's per-turn cost agreed with it within 1 % on 2026-11-11
(November: $107.12 ledger against $107.78 billed), so `credits_cost_factor` is 1.0; a first reading of 0.47 came
from summing cumulative session totals twice and was dropped. Since the 10th the ledger says about $4.40 against
$3.02 billed (a turn at the grant boundary bills the old grant): the cap errs on the safe side. The strip marks the
figures with "≈".

Zero debt: three brakes, in the order a turn meets them.

1. Start gate (`route.claim`, locked with the card's count of running credit turns): a start needs
   `spent + exposure < cap`, where each running credit turn counts for the larger of its live cost and a $2 reserve.
   Within $20 of the cap (`pacing.NEAR_CAP_USD`) at most one credit turn runs; a second goes to the plan (or waits).
   Many credit turns once ran at once while the grant ran out and billing lagged: that is the failure this stops.
2. Hard stop (`runner/creditguard.py`, the credit twin of the overage guard): the follower of every credit turn adds
   up its cost as assistant events arrive (`credits/meter.py`) and calls `route.watch`. When `spent + the live cost of
   all running credit turns >= cap`, every running credit turn is stopped at once (`handle.stop`), `cap_hit` is set,
   and `pipeline.turn` goes on in the same stage with the continue note on the plan route, resuming the same session
   (or pauses for the plan limit if there is one). The stopped turn has no result event, so its ledger line carries the
   usage estimate as its cost. Latency: the follower polls the stream every 50 ms (`adopt.POLL`) and the check runs in
   the event's own parse, so the stop fires within about 50 ms of the line plus the kill (about 4 ms measured between
   the stream write and the exit record in the fake harness). It is event-driven: a turn inside one very long model
   message shows no cost until that message's event arrives.
3. The $10 margin on the grant and the cap itself: week 4 may spend 190 of 200.

The live estimate prices the usage of each assistant message at Sonnet list prices (input and cache tokens exact,
output the larger of the reported count and a size estimate of the blocks). Against 77 real credit turns it ran about
twice the SDK's own totals (median 2.1; 5 of 77 below 1.0, the worst at 0.31): the safe side for a brake, and the
start gate plus the $10 margin cover the rare turn it undercounts.

`limit.credits` (`contracts/common.schema.json`, computed by the server, the page only shows it) carries
`route` (what a new turn takes now, null = waits), `period_start`, `week`, `monthly_usd`, `cap_usd`,
`spent_period_usd`, `credit_turns_period`, `remaining_usd`, `over_cap`, `running_credit_turns` and `cost_factor`.
The usage strip shows one bar of spent against the monthly grant, a tick at each weekly cap with the current one lit,
`≈$spent / $cap` and `≈$remaining`; names only in the tooltip (textgate).

## The ledger

`<run root>/credits-ledger.jsonl` (`credits/ledger.py`): one line per finished turn of either route,
`{stem, task, role, route, session_id, cumulative_usd, delta_usd, ended_at}`, appended through `atomic.append_line`
(`DOCS-resilience.md`). A result event's `total_cost_usd` is cumulative per session and a session mixes routes, so a
turn's own cost is its total minus the session's previous total (`ledger.delta`; a smaller positive total means the
counter restarted and counts whole). A turn with no result event (killed) is a turn at cost 0: the next turn of its
session pays the difference. When the file is missing the server rebuilds it once at start from the streams
(`ledger.load`, also children of an umbrella); recording a stem twice (a crash replay, a stream the backfill
saw) changes nothing. The summary is in memory: no request reads a stream. `result.json` of every turn now also
keeps the stream's `total_cost_usd` (null without a result event) and `model_usage` (T1990).

## Credit turns

`<sdk venv python> -m todoimpl.runner.sdkturn <spec>` runs under the same turn host, unit and adoption machinery
as a plan turn. The spec comes from the same `claude.options` as the plan argv (cwd, add_dirs, permission mode,
allow/deny tools, resume, hooks-off settings, env), plus model `sonnet` for every role (the feed and `state.extra.credit_downgrade` say when a role wanted more), `effort`, setting sources
user/project/local and the Claude Code system prompt. A transport subclass prints the CLI's raw stream-json events,
so `*.stream.jsonl` has the shape every parser expects. The plan env never has `ANTHROPIC_API_KEY` (it would beat
the plan login); the credit env carries it from the 0600 invoke file the host deletes at once. The SDK is pinned
in `deploy/requirements-sdk.txt`; `scripts/deploy.sh` creates `~/.local/share/todoImplementer/sdk-venv`
(`$TODOIMPL_SDK_VENV`) once and applies the pin. A missing venv shows as `unavailable` with that text.

## Credits exhausted

A credit turn that ends in a billing or key error ("Credit balance is too low", invalid key, spend limit) is not
retried: `credits-exhausted` is written until the limit's end, the run pauses (`paused_limit`) with the visible
reason "free API credits exhausted", and when the plan limit resets new turns use the plan again.

## A stored limit is re-checked

`limit-until` is a guess from the last rejected turn; plans reset early. `runner/limitprobe.py` asks the plan
itself (`usage/oauth.py`: the OAuth usage endpoint Claude Code's /usage reads, free, no turn; the token in
`~/.claude/.credentials.json` is only read, never refreshed, never logged) at start, every 5 min, and in the
background on a board request while a limit holds (at most once a minute). A usable plan (no full window) clears
`limit-until` and the exhausted mark, so the queue resumes within `IDLE_WAIT`; a full window moves the limit to
its real reset. An expired token or a failed call is "unknown" and changes nothing. The newest probe is kept in
`usage-probe.json`; the usage strip shows it while under 15 min old, and never shows a stream window past its
reset.

## Overage guard

A plan turn whose stream carries `rate_limit_event` with `isUsingOverage: true` is killed at once (`runner/guard.py`,
live in the stream follower), `limit-until` is set to the reset of the window at its limit (never the overage
window's own), `overage-alert.json` raises a red board banner until then. No desktop notification: alerts show
only inside todoImplementer. There is no per-task "Run on credits" and no way to spend overage.

## Manual work

A note title starting `MANUAL WORK REQUIRED:` is human work: status yours, assignee human, `start` disabled with
that reason, and `Scheduler.start` refuses it.

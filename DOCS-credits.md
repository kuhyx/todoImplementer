# Free API credits, routes and the overage guard

kuhy pays for the Max subscription and nothing else. The plan includes a monthly grant of API credits in a Console org
(no payment method, $0 purchased). Anthropic covers the Claude Agent SDK with it and does not cover the `claude`
CLI, so credit turns go through the SDK; the CLI is never run with the key and no SDK identity is spoofed.
Key lifecycle: `DOCS-apikey.md`. Code: `server/todoimpl/credits/`, `runner/credit.py`, `sdkturn.py`, `guard.py`.

## Routes

A turn takes one route, chosen when it actually starts (`credits.route.choose`): plan while no limit is active;
credits while the plan limit (`limit-until`) is active and the fallback is ready; otherwise it waits for the limit
(`paused_limit`). Any role continues on either route turn by turn: the session id, the cost and the run state are
shared, so a plan session resumes on credits and back. `state.extra.route`, `sessions[role].route`, the
`<stem>.route` file and `<stem>.result.json` record the route; the card shows a "free credits" badge and the feed
a line at each turn start.

Fallback is `ready` only when all hold: the global setting is on (default on; `~/.config/todoImplementer/
settings.json`, `$TODOIMPL_SETTINGS`; toggled on the board through `POST /api/settings/credits-fallback`
`{enabled}`, Origin + CSRF like every POST), the SDK venv exists, the key is usable (the monitor's cached status,
never a network call in a request or the queue) and the credits are not exhausted. The server words the state
(`off`, `ready`, `exhausted`, `unavailable`) in `limit.credits`; the page only shows it.

## Credit turns

`<sdk venv python> -m todoimpl.runner.sdkturn <spec>` runs under the same turn host, unit and adoption machinery
as a plan turn. The spec comes from the same `claude.options` as the plan argv (cwd, add_dirs, permission mode,
allow/deny tools, resume, hooks-off settings, env), plus model `sonnet` for every role, setting sources
user/project/local and the Claude Code system prompt. A transport subclass prints the CLI's raw stream-json events,
so `*.stream.jsonl` has the shape every parser expects. The plan env never has `ANTHROPIC_API_KEY` (it would beat
the plan login); the credit env carries it from the 0600 invoke file the host deletes at once. The SDK is pinned
in `deploy/requirements-sdk.txt`; `scripts/deploy.sh` creates `~/.local/share/todoImplementer/sdk-venv`
(`$TODOIMPL_SDK_VENV`) once and applies the pin. A missing venv shows as `unavailable` with that text.

## Credits exhausted

A credit turn that ends in a billing or key error ("Credit balance is too low", invalid key, spend limit) is not
retried: `credits-exhausted` is written until the limit's end, the run pauses (`paused_limit`) with the visible
reason "free API credits exhausted", and when the plan limit resets new turns use the plan again.

## Overage guard

A plan turn whose stream carries `rate_limit_event` with `isUsingOverage: true` is killed at once (`runner/guard.py`,
live in the stream follower), `limit-until` is set to the reset of the window at its limit (never the overage
window's own), `overage-alert.json` raises a red board banner until then. No desktop notification: alerts show
only inside todoImplementer. There is no per-task "Run on credits" and no way to spend overage.

## Manual work

A note title starting `MANUAL WORK REQUIRED:` is human work: status yours, assignee human, `start` disabled with
that reason, and `Scheduler.start` refuses it.

# Surviving multi-day runs

An umbrella run takes days (note 2d0704cd: 48 children, rounds of 1, 2, 4, 8). In that time the board can be
restarted or redeployed, a turn or worker can be killed, the PC can reboot or shut down, and the network can go
away. This file lists what is guaranteed, what keeps it true, and which test breaks when it stops being true.
Code: `server/todoimpl/atomic.py`, `runner/{retry,netwait,freeworker}.py`, `umbrella/{outage,run,rounds,workers}.py`,
`deploy/todoimplementer.service`, `scripts/deploy.sh`. Regression ids T1901 to T1907, T1988.

## Guarantees

| Event | What happens | Test |
|---|---|---|
| Board killed, restarted or deployed | Turns are their own units and keep running; the new server adopts them (`DOCS-spec.md`, "Turns outlive the server"). An umbrella resumes its round at the step it reached: a saved manager verdict is never asked for twice, and the pool starts each unfinished child once. | `tests/umbrella/test_flow_resume.py`, `tests/runner/test_runner_adopt.py` |
| Restart while a card or child was shipping | Every Ship survives it: the run is queued again in `shipping` and ships by itself, no second click, no Needs you. Ship is idempotent at every cut point (before the push, after it before `pushed.json`, mid-deploy, before the close, mid-rebase). A run found at `gate` (left by an older server) ships, or a closing one closes, at once (T2060). At most 2 automatic resumes per Ship (`restart.MAX_RESUMES`, counter `ship_resumes`); a ship that keeps restarting the board then fails "Ship was interrupted by a restart N times in a row: check origin and the note, then Retry", and Retry goes straight back to `shipping`. | `tests/runner/test_runner_ship_resume.py`, `tests/umbrella/test_restart_ship.py` (T1905, T1988) |
| Reboot or shutdown | The board unit and the transient turn units die; the board comes back at boot (below). A turn with no exit record and a dead host is lost: the same stage resumes the stored session (`claude --resume <id>`) with the kill note, or starts a fresh session with a handoff summary when it was idle for over an hour. Manager and children alike; nothing is started twice. | `tests/umbrella/test_reboot.py` (T1907), `tests/runner/test_runner_adopt.py` |
| Power cut during a write | Every state, round, mark, setting, plan and jsonl write goes through `todoimpl.atomic`: temp file, `fsync`, rename, directory `fsync` (appends are `fsync`ed). A reader sees the old file or the new one. A torn last line of a jsonl log is skipped by its readers. `tests/test_atomic.py` fails when a module renames a temp file by hand. | `tests/test_atomic.py` (T1901), `tests/umbrella/test_workers.py` |
| Turn killed by a signal (OOM, SIGKILL, host died) | Exit code below 0 or from 128 up, with no result event: the stage rests as `paused_retry` with reason `killed` and reruns on the ladder below, at most 5 times (`retry.MAX_KILL_RETRIES`), then Needs you ("The implement turn failed ..."). A crash with an error result keeps its 3 tries. | `tests/resilience/test_killed_turns.py` (T1902) |
| Manager killed | Same as above. It is never an escalation: `rounds._manage` re-raises `KilledError`, so no child goes to Opus; when the bound is spent the umbrella asks kuhy. | `tests/umbrella/test_resilience.py` (T1902) |
| Free worker killed | `freeworker` logs `{phase: "killed", symptom: "worker killed by a signal (exit N), attempt K"}` to `free-issues.jsonl`, waits 5 s times the attempt, and starts again, 3 attempts in all. A kill on every attempt exits 5 whatever the tree holds (the manager is told: finish the child, report `fixed`). Every attempt is a line of `free-workers.jsonl`. | `tests/umbrella/test_freeworker_kill.py` (T1903) |
| Internet down | Before a round's manager turn the server connects to `api.anthropic.com:443`, then `1.1.1.1:443` (2 s each). No answer: the umbrella rests in `paused_retry`, reason `network`, no turn is started and nothing fails or escalates. A turn that dies with a network error rests the same way. | `tests/umbrella/test_outage.py` (T1904), `tests/runner/test_runner_selfheal.py` |
| Gateway unreachable | `freegate.check` separates "nothing answered" (`unreachable`: refused, timed out) from "answered badly" (HTTP 503: not free, the manager does the child). Unreachable rests the round, reason `gateway`, and logs the probe error as phase `start`. | `tests/umbrella/test_outage.py` (T1904) |
| Todo app unreachable | The drive rests, reason `todo`, same ladder. | `tests/runner/test_runner_selfheal.py` |
| Todo MCP wedged or timing out | The client keeps one request on the wire; a timeout or connection error closes a gate for the transport's own short ladder (`Transport.LADDER`: 1, 2, 5, 10, 30 s, capped; not the minute ladder below), calls inside it fail at once and open no socket, each window ends with one probe, so the board is fresh within 30 s of the todo app returning; the cache refresh is single-flight. The board says `todo MCP not answering (timeout)`, and an HTTP error from a server that was just failing reads `not answering (HTTP 403 after timeouts)`, never "token rejected". | `tests/todo_mcp/test_outage.py` (T2005) |
| Deploy blocked by kuhy's edits in `~/src/<repo>` | Equal files are restored and the deploy reruns; his own edits are never touched, the run rests in `paused_retry` ("deploy waits: ...") for up to 12 ladder steps, then Needs you with the file names (`DOCS-landing.md`). | `tests/runner/test_runner_deploy_heal.py` (T2007) |
| Plan usage limit | Unchanged: `paused_limit` until `resume_at`; `runner/limitprobe.py` asks the OAuth usage endpoint at start, every 5 min and on a board request, and lifts a limit the plan no longer backs (`DOCS-credits.md`). | `tests/runner/test_runner_limitprobe.py` |

## The backoff ladder

`retry.delay(n)`: 1, 2, 5, 10 minutes, then every 30 minutes without end (`DEFAULT_BACKOFF`, `DEFAULT_LONG_WAIT`).
The counter is `retries` (reset by a finished turn); the umbrella's outage waits count `net_retries` and
`gw_retries` and clear them when the thing answers again. A paused run is requeued at the front and held until
its `resume_at`; a note from kuhy ends the wait. The reason is `state.extra.retry_kind`: `network`, `gateway`,
`killed`, `crash`, `todo` or `turn`; the tracking view (`DOCS-tracking.md`) shows it as an icon.

## Boot and restart policy (read on the real system, 2026-11-10, read-only)

- Lingering: `loginctl show-user kuhy -p Linger` is `yes`. `scripts/deploy.sh` now checks it every deploy and
  turns it on (`loginctl enable-linger`), failing loudly when it stays off.
- `todoimplementer.service` is `enabled`, `WantedBy=default.target`. The installed copy still says
  `Restart=on-failure` with the default start limit (5 starts in 10 s). The repo unit is now `Restart=always`
  (a stray SIGTERM restarts it too; `systemctl --user stop` does not) with `StartLimitIntervalSec=0` (a crash
  loop while the todo app is still down after boot never gives up). The next `scripts/deploy.sh` installs it;
  this work did not deploy.
- Turn units are transient (`systemd-run --user --collect`): they do not survive a reboot, which is why the
  lost-turn resume above exists. `todo-mcp.service` is enabled.
- The gateway container `omniroute` has restart policy `unless-stopped` and `docker.service` is enabled, so it
  returns after boot on its own; until it does, rounds rest with reason `gateway`.
- The run state lives on ext4 (`/`), where rename without `fsync` is not safe against a power cut: hence the
  helper.

## Not covered

- A Ship while offline or while origin is unreachable fails the child with the push error and asks kuhy; it is a
  click of his, so it is not retried by itself.
- A reboot in the middle of a Ship click leaves the umbrella `failed` ("Ship was interrupted"); check origin, then
  Retry.
- The 1, 2, 5, 10, 30 ladder is shared by every run; there is no per-run setting.

## Resource cap

Every turn, gate and deploy unit joins `todoimpl.slice` (`deploy/todoimpl.slice`, installed by `scripts/deploy.sh`):
`MemoryHigh` 14G (reclaim pressure), `MemoryMax` 18G, `MemorySwapMax` 8G, `CPUQuota` 1600 %, `CPUWeight` 20,
`TasksMax` 8192. Many parallel builds once filled RAM and 43 GB of swap and froze the PC (T1982). Past the cap the
kernel OOM-kills inside the slice, never the desktop; the killed turn is a failed turn and the retry ladder resumes it.

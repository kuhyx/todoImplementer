# One part per error: twins, same issues, sources

kuhy (2026-11-27): "the same issues should be merged together into one", for every repo that reports errors to
the board. Code: `server/todoimpl/errors/twin.py` (before a part is made), `errors/repair.py` (twins already made),
`errors/ticket.py` (`Seen:` per signature). Regressions T2570, T2571 (`tests/regressions/DOCS-errors.md`).

## Why kartka's card showed every `[sig8]` twice (T2570)

The errors loop ticks at once when the server starts, but the board's cards come from the first full fetch
(about 30 s, longer while the todo MCP is down). On 2026-11-25 22:37 the PC booted with the MCP down for about
50 s: the ticks at 22:37:05 and 22:38:05 saw no cards, so every open ticket counted as "closed by hand" for two
ticks (`MISSING_TICKS`) and was made again. The ingest at 22:38:57 then raised the counts on the first copy only,
which is why one twin of 971debc8 still reads 19x and one of 64f0bd6f reads 1x. Since T2482 (2026-11-22) the todo
app takes two parts with one title, so nothing refused the twin. book-guard's card got its twins the same night.

## The rules now

- **Before any new part** (`_create`: a new error, a lost ledger, a part missing two ticks, a reopen) the loop
  reads the repo's open notes from the todo app itself (`twin.lookup`), never the board's cache. An open part
  that carries the `Error-Signature:` line takes the record; no part is made. A todo app that cannot answer
  makes nothing that tick.
- **Same issue, one part.** Two records are one issue when they are of one app and their `Error:` lines (kind and
  the whole masked message) are equal. The second one's block (from its `Error:` line to its signature line) is
  appended to the open part of the first, so one part holds several `Error-Signature:` lines. Ship marks every
  signature of a ticked part shipped and the source resolves each one. Kept apart: a different kind or message
  (`slow wait: reader.open` and `slow wait: reader.chapter` are two waits; `updates.check timeout` and
  `updates.check HTTP error <n>` are two failures).
- **One `Seen:` line per signature** (T2571). In a part with several signatures each block starts after the
  previous signature line or `### ` heading; the loop rewrites the count in that block only. A closed section is
  never rewritten.
- **Twins already made** (`repair.fold`, every tick, after the tickets): on each open card with no live run, the
  open parts that share a signature or an issue form a group. The first stays; each other one gives the kept part
  any signature it lacks, then is closed in place: `closed: duplicate of <key>: one part per error signature
  (T2570)`. Closing in place renumbers no section, so run dirs and ticks stay right. A ledger entry of a closed
  twin gets the kept part's title and count 0, so the next tick writes the current count. A card at work is left
  until it rests; a closed twin is skipped next time, so the fold runs once.

## Sources that report on their own

| Source | Writes | Signature | Stable? |
| --- | --- | --- | --- |
| book-guard, diet-guard-gate, kartka, leetcode-guard, screen-locker, todo, tunedeck, tutor (and any app with `/<app>/errors` in RTDB or a spool file, e.g. logo-review) | kuhyx/utils `app_errors` ingest (`app-errors-ingest.timer`, every 5 min): `~/.local/state/app-errors/<app>.json` | `app_errors/signature.py`: error type + message with numbers, ids and URLs masked (max 160 chars) + first app frame without line numbers, else route, else kind; a slow wait is route + operation | Yes. The only splits of one message are by design: kartka's `perf.slow` per route (`browse.nextpage`, `details.refresh`) and book-guard's `freedays` error from two call sites. The board now puts those in one part. |
| todoimplementer | the board's stall watch (`stall/`): `app-errors/todoimplementer.json` | `stall-<cause>` | Yes (a fixed set of causes) |
| heavy builds | `runner/heavybuild.py`: `app-errors/heavy-builds.json` | `heavy-<tool>-<step>` | Yes |
| slow gate steps | `stall/slowstep.py`: `app-errors/slow-steps.json` | `slow-<step>` | Yes |
| stray work | `runner/stray.py`: `app-errors/stray-work.json` | `<sha256(patch)[:12]>-stray` | Yes (same patch, same signature) |
| kartka adapter (`~/.local/state/kartka-errors/state.json`) | kartka's retired own ingest | kartka's port of the same function | Off: `settings.json` has `error_sources: []`; the file stopped on 2026-11-17 |

kartka needs no change and no release: the app sends raw reports and the shared ingest signs them. Changing a
signature function would give every open ticket a new key (a full second set of parts, fixed states orphaned).

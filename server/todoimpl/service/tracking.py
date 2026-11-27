"""The service side of /api/umbrella/<id>: the umbrella's run, its child rows, the track object, worker logs.

`ServiceBackend` binds `umbrella` and `worker_log` from here as its methods.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from todoimpl.board.card import build_card
from todoimpl.board.parse import StateError
from todoimpl.board.state import load, run_dir
from todoimpl.nolimit import status as nolimit
from todoimpl.umbrella import issues as issue_log
from todoimpl.umbrella import track
from todoimpl.umbrella.store import RECORD, children_root
from todoimpl.umbrella.view import rows as child_rows
from todoimpl.usage import usage_summary

from .runtitles import card_titles

if TYPE_CHECKING:
    from .backend import ServiceBackend


def issues(backend: ServiceBackend, id8: str) -> str | None:
    """Return the raw free-model issue log of a known task (GET /api/task/<id8>/issues), else None."""
    if not any(t.id == id8 for t in backend.cache.snapshot().tasks):
        return None
    return issue_log.raw(run_dir(backend.root, id8))


def usage(backend: ServiceBackend) -> dict[str, Any]:
    """Return GET /api/usage: plan windows, cost, autonomy, the cached gateway reading, the no-limit row."""
    known = backend.cache.run_titles.titles() if backend.cache.run_titles else {}
    titles = {**known, **card_titles(backend.cache.snapshot().tasks)}
    found = usage_summary(backend.root, backend._clock(), titles)  # noqa: SLF001
    if backend.gateway is not None:  # a cached reading: no request waits on the gateway
        found["free"] = backend.gateway.view()
    found["nolimit"] = nolimit.view(backend.root)
    return found


def umbrella(backend: ServiceBackend, id8: str) -> dict[str, Any] | None:
    """Return the tracking view of card `id8` (GET /api/umbrella/<id8>); None without an umbrella run."""
    found = next((t for t in backend.cache.snapshot().tasks if t.id == id8), None)
    directory = run_dir(backend.root, id8)
    try:
        run = load(directory)
    except StateError:
        return None
    if found is None or run is None or RECORD not in run.extra:
        return None
    ctx = backend._context()  # noqa: SLF001 - the service's own context builder
    until = ctx.limit.until if ctx.limit.holds else None
    rows, _ = child_rows(directory, run, live=id8 in ctx.live, limit_until=until)
    card = build_card(found, backend._with_extras(run), ctx)  # noqa: SLF001
    now = backend._clock()  # noqa: SLF001
    return track.build(track.Run(id8, found.title, card["status"], directory), run, rows, now)


def worker_log(backend: ServiceBackend, id8: str, child: str) -> str | None:
    """Return the tail of the newest worker log of `child` under umbrella `id8`, None when there is none."""
    directory = run_dir(backend.root, id8)
    if not (children_root(directory) / child).is_dir():
        return None
    return track.log_tail(directory, child)

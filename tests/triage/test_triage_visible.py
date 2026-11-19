"""A label shows on the board when it is written, and the real fetch reads triage.json (kuhy, 2026-11-19)."""

from collections.abc import Callable

from conftest import Triage
from servicefakes import Rig
from todoimpl.board.state import run_dir
from todoimpl.triage import label

Make = Callable[..., Triage]
NAMES = ("manual one", "new app", "reading", "everywhere")


def test_t2074_a_label_shows_on_the_board_at_once_not_after_the_next_30_s_fetch(
    rig: Rig, triage: Make
) -> None:
    """A label is a file, not a note change: nothing woke the cache, so the card stayed Yours till a fetch."""
    manual, new, research = (rig.note(t, repo=None) for t in NAMES[:3])
    pass_ = triage(
        {"label": "manual", "reason": "a puzzle"},
        {"label": "new_repo", "name": "pacman-gui", "reason": "new app"},
        {"label": "research", "reason": "links"},
    )
    assert pass_.service.tick() + pass_.service.tick() == 3  # PER_TICK is 2
    # no cache.refresh() here: the board answers from the snapshot, as it does for the page
    shown = {c["id"]: c for c in rig.backend.board()["tasks"]}
    assert (shown[manual]["triage"], shown[manual]["status"]) == ("manual", "yours")
    assert (shown[new]["triage"], shown[new]["status"]) == ("new_repo", "backlog")
    assert (shown[research]["triage"], shown[research]["status"]) == ("research", "backlog")
    assert "start" in {a["id"] for a in shown[research]["actions"]}


def test_t2075_the_real_fetch_reads_triage_json_from_the_run_dir(rig: Rig) -> None:
    """Fake todo MCP plus triage.json files on disk, then the real board fetch: the whole path, no stub."""
    ids = {name: rig.note(name, repo=None) for name in NAMES}
    for name, found in zip(NAMES, ("manual", "new_repo", "research"), strict=False):
        label.save(run_dir(rig.root, ids[name]), label.Verdict(found, name="x-app"), "d", 1.0)
    rig.backend.cache.refresh()
    board = {c["id"]: c for c in rig.backend.board()["tasks"]}
    assert [board[ids[n]].get("triage") for n in NAMES] == ["manual", "new_repo", "research", None]
    assert [board[ids[n]]["status"] for n in NAMES] == ["yours", "backlog", "backlog", "yours"]

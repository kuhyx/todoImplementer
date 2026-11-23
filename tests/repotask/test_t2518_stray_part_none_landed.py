"""T2518: a stray-work part ticked with no commit ("none worth landing") closes and is never filed again."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from repofakes import PLAN, Rig, live_for
from runnerfakes import sh
from schedfakes import reply
from test_flow import tick_before_start
from todoimpl.errors import ledger
from todoimpl.errors.ticket import STRAY_DONE, STRAY_GOAL
from todoimpl.repotask.ids import repo_card_id
from todoimpl.runner import appfix, stray

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.todo_mcp.items import Item

KEY = f"demo:0123456789ab{stray.SUFFIX}"
NONE = reply("none of it is worth landing, because origin already does it better\n\nD: done")


def test_t2518_a_stray_part_with_nothing_worth_landing_closes_cleanly(rig: Rig) -> None:
    repo = rig.repo()
    body = f"{STRAY_GOAL}\n{STRAY_DONE}\nError-Signature: {KEY}\ndone_check: true"
    note = rig.note(repo, "Stray work in demo", body)
    card = repo_card_id(repo)
    ledger.put(rig.world.root, KEY, state="ticket", repo=repo, title="Stray work in demo", count=1, starts=1)
    remote = rig.world.tmp / "remotes" / "demo.git"
    before = sh(remote, "git", "rev-parse", "main").strip()
    rig.script(card, PLAN, NONE, live_for(f"{note}-0"))
    tick_before_start(rig, card, f"{note}-0")
    rig.sched.start(card)
    rig.wait(card, {"gate"})
    rig.sched.ship(card)
    st = rig.wait(card, {"shipped"})
    assert st.error is None
    assert st.ship is not None
    assert st.ship["commit"] == ""
    assert sh(remote, "git", "rev-parse", "main").strip() == before  # nothing pushed, nothing deployed
    closed = next(n for key, n in rig.fake.store.notes.items() if key.startswith(note))
    assert closed.status == "done"
    assert str(closed.evidence).startswith("Closed with no code change.")
    assert (
        ledger.load(rig.world.root)[KEY]["state"] == "shipped"
    )  # the errors loop resolves it, never re-files


def test_t2518_with_no_commit_only_stray_tickets_count_as_shipped(tmp_path: Path) -> None:
    other = (
        "kartka:02b0d43d9f"  # an app error closed with no code change is not fixed: the loop files it again
    )
    for key in (KEY, other):
        ledger.put(tmp_path, key, state="ticket", repo="kuhyx/demo", title="t", count=1, starts=1)
    item = cast("Item", SimpleNamespace(parts=(), body=f"Error-Signature: {KEY}\nError-Signature: {other}"))
    appfix.shipped(tmp_path, tmp_path, item, "", 5.0)
    states = {key: entry["state"] for key, entry in ledger.load(tmp_path).items()}
    assert states == {KEY: "shipped", other: "ticket"}

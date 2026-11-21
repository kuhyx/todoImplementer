"""The cheap tier on a repo card (T1999): a textgate part hides behind the repo-name title."""

from __future__ import annotations

from typing import Any

from repofakes import IMPL, LIVE, PLAN, Rig, live_for
from schedfakes import reply
from tierfakes import Free
from todoimpl.repotask import files
from todoimpl.repotask.ids import repo_card_id
from todoimpl.runner.files import write_json

TEXTGATE = (
    "## Make demo text-free (textgate-rework)\nUse skill textgate-rework. Scan: 7 items.\ndone_check: true"
)
PLAIN = "## Fix the parser\nHandle empty input.\ndone_check: true"


def implement_calls(rig: Rig) -> list[dict[str, Any]]:
    return [c for c in rig.world.calls() if "Implement stage" in str(c["prompt"])]


def run_to_gate(rig: Rig, repo: str, *note_ids: str) -> tuple[str, Any]:
    """Tick the notes' first parts (the fake claude cannot run the tick command), start, wait for the gate."""
    card = repo_card_id(repo)
    keys = [f"{n}-0" for n in note_ids]
    write_json(rig.run_dir(card) / files.DONE, {"done": keys, "steps": {}})
    rig.script(card, PLAN, IMPL, live_for(*keys))
    rig.sched.start(card)
    return card, rig.wait(card, {"gate"})


def test_t1999_a_textgate_part_on_a_repo_card_runs_on_the_free_workers(rig: Rig, free: Free) -> None:
    repo = rig.repo()
    note = rig.note(repo, "demo todos", TEXTGATE)
    assert rig.card(repo)["tier"]["cheap"] is True  # the badge reads the parts, not the repo-name title
    card, st = run_to_gate(rig, repo, note)
    impl = implement_calls(rig)
    assert [c["model"] for c in impl] == ["opus"]
    assert "todoimpl.runner.freeworker" in str(impl[0]["prompt"])  # the manager addendum
    assert "textgate" in str(impl[0]["prompt"]).lower()
    assert (st.extra["tier"], st.extra["free_models"]) == ("cheap", True)
    assert free.checked() == [st.worktree]
    assert rig.card(repo)["tier"]["cheap"] is True
    assert card == st.task_id


def test_t1999_a_part_with_a_tier_line_is_still_cheap(rig: Rig, free: Free) -> None:
    repo = rig.repo()
    note = rig.note(repo, "demo todos", "## Rename it\nRename foo to bar.\nTier: cheap\ndone_check: true")
    _, st = run_to_gate(rig, repo, note)
    assert st.extra["tier"] == "cheap"
    assert "todoimpl.runner.freeworker" in str(implement_calls(rig)[0]["prompt"])


def test_t1999_an_ordinary_repo_card_stays_on_the_normal_tier(rig: Rig, free: Free) -> None:
    repo = rig.repo()
    note = rig.note(repo, "demo todos", PLAIN)
    assert rig.card(repo)["tier"]["cheap"] is False
    _, st = run_to_gate(rig, repo, note)
    assert st.extra["tier"] == "normal"
    assert "freeworker" not in str(implement_calls(rig)[0]["prompt"])
    assert free.checked() == []


def test_t1999_a_card_with_a_textgate_part_among_others_is_cheap(rig: Rig, free: Free) -> None:
    repo = rig.repo()
    first = rig.note(repo, "plain note", PLAIN)
    second = rig.note(repo, "demo todos", TEXTGATE)
    _, st = run_to_gate(rig, repo, first, second)
    assert st.extra["tier"] == "cheap"


def test_t1999_a_new_cycle_decides_the_tier_again(rig: Rig, free: Free) -> None:
    repo = rig.repo()
    first = rig.note(repo, "plain note", PLAIN)
    card, st = run_to_gate(rig, repo, first)
    assert st.extra["tier"] == "normal"
    rig.sched.ship(card)
    rig.wait(card, {"shipped"})
    rig.note(repo, "demo todos", TEXTGATE)  # the repo gets new work: same card id, next cycle
    nudges = (reply("one part is left\n\nD: done"), reply("still one\n\nD: done"))
    rig.script(card, PLAN, IMPL, *nudges, LIVE)
    rig.sched.start(card)
    again = rig.wait(card, {"gate"})
    assert (again.extra["cycle"], again.extra["tier"]) == (2, "cheap")
    assert any("freeworker" in str(c["prompt"]) for c in implement_calls(rig))
    assert rig.card(repo)["tier"]["cheap"] is True

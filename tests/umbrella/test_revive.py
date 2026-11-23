"""T2344: children that already failed for a reason Claude can fix are picked up again on server start."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from runnerfakes import Notes
from todoimpl.board import state as store
from todoimpl.runner import recovery
from todoimpl.umbrella.store import child_dir

if TYPE_CHECKING:
    from pathlib import Path

CARD = "umbr0001-0"
KILLED = "Pre-push gate step ci-mirror is red (exit -15):\nCI mirror (tests, shard 1/6)........"
WAITED = "Pre-push gate step shard-0 is red (exit -15):\nwaiting for build lock held by x; 2 ahead\n"
NO_LINE = "pushed, not deployed: kuhyx/cv declares no deploy: command in CLAUDE.md"
DEPLOY_34 = "pushed, not deployed: deploy failed (exit 34): FAILURE: Build failed"
DEPLOY_15 = "pushed, not deployed: deploy failed (exit -15): kotlin_version"
KUHY = "Rebase on origin/main conflicts in a.txt: resolve it in /wt, then Retry"


def _child(run_dir: Path, n: int, error: str, **extra: object) -> str:
    cid = f"umbr0001-{n}"
    st = store.RunState(task_id=cid, stage="failed", repo=f"kuhyx/r{n}", error=error)
    st.extra.update(umbrella_round=1, failed_stage="shipping", **extra)
    store.save(child_dir(run_dir, cid), st)
    return cid


def _world(root: Path) -> dict[str, str]:
    run_dir = root / CARD
    um = store.RunState(task_id=CARD, stage="failed", error="6 of 7 children need you: ...")
    um.extra.update(failed_stage="implement", umbrella={"width": 2, "kids": [], "rounds": []})
    store.save(run_dir, um)
    deploy = child_dir(run_dir, "umbr0001-5") / "deploy"
    deploy.mkdir(parents=True)
    (deploy / "exit.json").write_text(
        json.dumps({"exit": 34, "tail": "FAILURE: Build failed\nkotlin_version 1.6 is too old", "log": "l"}),
        encoding="utf-8",
    )
    return {
        "killed": _child(run_dir, 1, KILLED),
        "waited": _child(run_dir, 2, WAITED),
        "no_line": _child(run_dir, 3, NO_LINE),
        "killed_deploy": _child(run_dir, 4, DEPLOY_15),
        "red_deploy": _child(run_dir, 5, DEPLOY_34),
        "kuhy": _child(run_dir, 6, KUHY),
        "spent": _child(run_dir, 7, NO_LINE, deploy_fixes=2),
    }


def _load(root: Path, cid: str) -> store.RunState:
    st = store.load(child_dir(root / CARD, cid))
    assert st is not None
    return st


def test_t2344_a_failed_umbrella_with_fixable_children_is_queued_again_on_start(tmp_path: Path) -> None:
    kids = _world(tmp_path)
    assert recovery.interrupted(tmp_path, Notes()) == [CARD]
    um = store.load(tmp_path / CARD)
    assert um is not None
    assert (um.stage, um.error, "failed_stage" in um.extra) == ("implement", None, False)
    for key in ("killed", "waited", "killed_deploy"):  # a plain rerun of the Ship first
        st = _load(tmp_path, kids[key])
        assert (st.stage, st.error, "failure_tail" in st.extra) == ("shipping", None, False), key
    for key, text in (("no_line", "- deploy: none (<why>)"), ("red_deploy", "kotlin_version 1.6 is too old")):
        st = _load(tmp_path, kids[key])
        assert (st.stage, st.error, st.extra["reship"]) == ("implement", None, True), key
        assert text in str(st.extra["failure_tail"]), key
    for key in ("kuhy", "spent"):  # kuhy's own step, and a child whose fix turns ran out, stay as they are
        st = _load(tmp_path, kids[key])
        assert (st.stage, st.extra.get("deploy_fixes", 0)) == ("failed", 2 if key == "spent" else 0), key


def _fail_again(root: Path, cid: str, error: str) -> None:
    st = _load(root, cid)
    st.stage, st.error = "failed", error
    st.extra["failed_stage"] = "shipping"
    store.save(child_dir(root / CARD, cid), st)
    um = store.load(root / CARD)
    assert um is not None
    um.stage = "failed"
    store.save(root / CARD, um)


def test_t2344_the_counts_are_saved_so_restarts_never_revive_without_end(tmp_path: Path) -> None:
    kids = _world(tmp_path)
    recovery.interrupted(tmp_path, Notes())
    assert _load(tmp_path, kids["killed"]).extra["gate_kills"] == 1
    _fail_again(tmp_path, kids["killed"], KILLED)
    _fail_again(tmp_path, kids["no_line"], NO_LINE)
    assert recovery.interrupted(tmp_path, Notes()) == [CARD]
    killed = _load(tmp_path, kids["killed"])  # killed twice: the session makes the step fit
    assert (killed.stage, killed.extra["ship_fixes"]) == ("implement", 1)
    assert "shard it finer" in str(killed.extra["failure_tail"])
    assert _load(tmp_path, kids["no_line"]).extra["deploy_fixes"] == 2
    _fail_again(tmp_path, kids["no_line"], NO_LINE)
    for cid in kids.values():
        if _load(tmp_path, cid).stage != "failed":
            _fail_again(tmp_path, cid, KUHY)
    assert recovery.interrupted(tmp_path, Notes()) == []  # every budget is spent or the step is kuhy's
    assert _load(tmp_path, kids["no_line"]).stage == "failed"


def test_t2344_a_failed_umbrella_with_nothing_fixable_stays_failed(tmp_path: Path) -> None:
    run_dir = tmp_path / CARD
    um = store.RunState(task_id=CARD, stage="failed", error="1 of 1 children need you: ...")
    um.extra.update(failed_stage="implement", umbrella={"width": 1, "kids": [], "rounds": []})
    store.save(run_dir, um)
    _child(run_dir, 1, KUHY)
    assert recovery.interrupted(tmp_path, Notes()) == []
    again = store.load(run_dir)
    assert again is not None
    assert again.stage == "failed"


def test_t2344_a_child_whose_state_does_not_parse_is_left_alone(tmp_path: Path) -> None:
    kids = _world(tmp_path)
    broken = child_dir(tmp_path / CARD, "umbr0001-9")
    broken.mkdir(parents=True)
    (broken / "state.json").write_text("{not json", encoding="utf-8")
    assert recovery.interrupted(tmp_path, Notes()) == [CARD]
    assert _load(tmp_path, kids["no_line"]).stage == "implement"
    assert (broken / "state.json").read_text(encoding="utf-8") == "{not json"

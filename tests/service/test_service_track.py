"""The tracking view of an umbrella through the service: counts, rounds, children, issues, ETA, logs."""

from __future__ import annotations

from typing import Any

from contract_lib import validate
from servicefakes import Rig
from test_service_umbrella import BODY
from todoimpl.board.state import RunState, run_dir, save
from todoimpl.umbrella import issues, workers
from todoimpl.umbrella.store import child_dir

NOW = 10_000.0


def _umbrella(rig: Rig, **record: Any) -> tuple[str, Any]:
    card = rig.note("Make the repos text-free", BODY, repo="kuhyx/hub")
    run = rig.run(card, "implement", worktree=str(rig.root / card))
    kids = [
        {"id": "aaaa1111-0", "repo": "kuhyx/alpha", "title": "Alpha text", "done": False},
        {"id": "bbbb2222-0", "repo": "kuhyx/beta", "title": "Beta text", "done": False},
        {"id": "cccc3333-0", "repo": "kuhyx/gamma", "title": "Gamma", "done": False},
    ]
    first = {"id": "aaaa1111-0", "verdict": "clean", "detail": "", "free": True, "checks": True, "ok": True}
    rounds = [{"n": 1, "width": 1, "next": 2, "children": [first], "started": 100.0, "ended": 700.0}]
    run.extra["umbrella"] = {
        "width": 2,
        "tier": "cheap",
        "kids": kids,
        "rounds": rounds,
        "current": None,
        **record,
    }
    save(run_dir(rig.root, card), run)
    return card, run_dir(rig.root, card)


def _child(directory: Any, cid: str, stage: str, **fields: Any) -> RunState:
    child = RunState(task_id=cid, stage=stage, **fields)
    save(child_dir(directory, cid), child)
    return child


def test_the_track_validates_and_counts_children_rounds_and_needs(rig: Rig) -> None:
    card, directory = _umbrella(rig)
    _child(directory, "aaaa1111-0", "gate", started_at=100.0, updated=1900.0)
    _child(directory, "bbbb2222-0", "failed", error="boom", started_at=200.0, updated=300.0)
    track = rig.backend.umbrella(card)
    assert track is not None
    validate("track", track)
    assert (track["id"], track["stage"], track["needs"]) == (card, "implement", 1)
    assert track["counts"]["total"] == 3
    assert track["counts"]["ready"] == 1
    assert track["rounds"][0]["children"][0]["repo"] == "kuhyx/alpha"
    assert (track["rounds"][0]["started"], track["rounds"][0]["ended"]) == (100.0, 700.0)
    assert track["round"] is None
    assert [k["repo"] for k in track["kids"]] == ["kuhyx/alpha", "kuhyx/beta", "kuhyx/gamma"]
    assert track["kids"][2]["elapsed"] is None  # not started


def test_elapsed_runs_for_a_working_child_and_stops_at_the_gate(rig: Rig) -> None:
    card, directory = _umbrella(rig)
    _child(directory, "aaaa1111-0", "gate", started_at=100.0, updated=1900.0)
    _child(directory, "bbbb2222-0", "implement", started_at=NOW - 50)
    rig.backend._clock = lambda: NOW
    track = rig.backend.umbrella(card)
    assert track is not None
    assert track["kids"][0]["elapsed"] == 1800.0
    assert track["kids"][1]["elapsed"] == 50.0


def test_the_eta_is_the_median_finished_child_times_the_batches_left(rig: Rig) -> None:
    card, directory = _umbrella(rig)
    assert rig.backend.umbrella(card)["eta"]["seconds"] is None  # type: ignore[index]
    _child(directory, "aaaa1111-0", "gate", started_at=0.0, updated=1800.0)
    track = rig.backend.umbrella(card)
    assert track is not None
    assert track["eta"] == {"seconds": 1800.0, "done": 1, "left": 2, "median": 1800.0, "width": 2}


def test_the_round_in_progress_names_its_step(rig: Rig) -> None:
    cur = {"n": 2, "width": 2, "ids": ["bbbb2222-0"], "started": 50.0, "free": {}, "failed": {}}
    for verdicts, checks, step in ((None, None, "manager"), ({}, None, "checks"), ({}, {}, "verdict")):
        card, _ = _umbrella(rig, current={**cur, "verdicts": verdicts, "checks": checks})
        track = rig.backend.umbrella(card)
        assert track is not None
        assert track["round"] == {"n": 2, "width": 2, "started": 50.0, "step": step, "ids": ["bbbb2222-0"]}


def test_a_run_that_waits_says_why_and_until_when(rig: Rig) -> None:
    card, directory = _umbrella(rig)
    run = RunState(task_id=card, stage="paused_retry", resume_at=NOW + 60, extra=_umbrella_extra(rig, card))
    run.extra["retry_kind"] = "network"
    save(directory, run)
    child = _child(directory, "aaaa1111-0", "paused_limit", resume_at=NOW + 5)
    track = rig.backend.umbrella(card)
    assert track is not None
    assert track["resting"] == {"kind": "network", "until": NOW + 60}
    assert track["kids"][0]["resting"] == {"kind": "limit", "until": NOW + 5}
    child.stage = "paused_retry"
    save(child_dir(directory, "aaaa1111-0"), child)
    track = rig.backend.umbrella(card)
    assert track is not None
    assert track["kids"][0]["resting"]["kind"] == "turn"  # no kind recorded: a plain transient failure


def _umbrella_extra(rig: Rig, card: str) -> dict[str, Any]:
    from todoimpl.board.state import load  # noqa: PLC0415

    found = load(run_dir(rig.root, card))
    assert found is not None
    return dict(found.extra)


def test_issues_are_grouped_by_phase_and_model_with_the_last_one_per_child(rig: Rig) -> None:
    card, directory = _umbrella(rig)
    for i in range(25):
        issues.append(
            directory, float(i), "kuhyx/alpha", "edit", f"bad {i}", "redid", fixed=i % 2 == 0, model="m1"
        )
    issues.append(directory, 99.0, "kuhyx/beta", "start", "no gateway")
    track = rig.backend.umbrella(card)
    assert track is not None
    validate("track", track)
    big, small = track["issues"]["groups"]
    assert (big["phase"], big["model"], big["count"], big["fixed"]) == ("edit", "m1", 25, 13)
    assert len(big["lines"]) == 20
    assert '"bad 24"' in big["lines"][-1]
    assert (small["phase"], small["model"]) == ("start", None)
    assert track["issues"]["total"] == 26
    assert track["kids"][0]["last_issue"]["symptom"] == "bad 24"
    assert track["kids"][2]["last_issue"] is None


def test_worker_attempts_and_logs_show_on_the_child(rig: Rig) -> None:
    card, directory = _umbrella(rig)
    cdir = child_dir(directory, "aaaa1111-0")
    cdir.mkdir(parents=True)
    (cdir / "worker-1.log").write_text("first\n", encoding="utf-8")
    (cdir / "worker-10.log").write_text("x" * 70_000 + "TAIL", encoding="utf-8")
    (cdir / "worker-x.log").write_text("ignored", encoding="utf-8")
    for killed in (True, False):
        workers.record(directory, {"child": "kuhyx/alpha", "killed": killed})
    track = rig.backend.umbrella(card)
    assert track is not None
    assert (track["kids"][0]["attempts"], track["kids"][0]["killed"], track["kids"][0]["log"]) == (2, 1, True)
    assert track["kids"][1]["log"] is False
    tail = rig.backend.worker_log(card, "aaaa1111-0")
    assert tail is not None
    assert tail.endswith("TAIL")
    assert len(tail) <= 64 * 1024
    assert rig.backend.worker_log(card, "bbbb2222-0") is None  # no such child dir
    (child_dir(directory, "bbbb2222-0")).mkdir(parents=True)
    assert rig.backend.worker_log(card, "bbbb2222-0") is None  # a dir without a log


def test_no_umbrella_run_means_no_track(rig: Rig) -> None:
    card = rig.note("Make the repos text-free", BODY, repo="kuhyx/hub")
    assert rig.backend.umbrella(card) is None  # no run yet
    rig.run(card, "implement")
    assert rig.backend.umbrella(card) is None  # a run without an umbrella record
    assert rig.backend.umbrella("zzzzzzzz-9") is None  # unknown card
    (run_dir(rig.root, card) / "state.json").write_text("{nope", encoding="utf-8")
    assert rig.backend.umbrella(card) is None  # unreadable state

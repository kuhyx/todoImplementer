# ruff: noqa: S108, S311
"""RunState load/save: strict parsing, round trip, atomic and locked writes."""

import json
import random
import threading
from pathlib import Path
from typing import Any

import pytest
from contract_lib import validate
from todoimpl.board import state
from todoimpl.board.parse import StateError
from todoimpl.board.state import RunState, SpecQuestion

FIXTURE = Path(__file__).parent.parent / "fixtures" / "state.json"


def random_state(rng: random.Random) -> RunState:
    def maybe(value: Any) -> Any:
        return value if rng.random() < 0.5 else None

    return RunState(
        task_id="".join(rng.choices("abcdef0123456789", k=8)) + f"-{rng.randrange(4)}",
        stage=rng.choice(state.STAGES),
        assignee=rng.choice(state.ASSIGNEES),
        session_id=maybe(f"sess-{rng.randrange(10**6)}"),
        worktree=maybe("/tmp/w"),
        branch=maybe("todoimpl/x"),
        cost_usd=round(rng.random() * 9, 4),
        spec_questions=[
            SpecQuestion(f"Q{i}", f"t{i}", "b", "r", maybe("a")) for i in range(rng.randrange(3))
        ],
        last_tag=rng.choice([*state.TAGS, None]),
        error=maybe("boom"),
        updated=round(rng.random() * 2e9, 3),
        repo=maybe("demo"),
        base_sha=maybe("abc"),
        head_sha=maybe("def"),
        started_at=maybe(1.5),
        resume_at=maybe(2.5),
        sessions=rng.choice([{}, {"plan": {"session_id": "s", "last_turn_end": 1.0}}]),
        self_check=rng.choice([[], [{"criterion": "c", "done": True}]]),
        checks=maybe(
            {"passed": True, "ran_at": 1.0, "results": [{"command": "make", "exit": 0, "tail": "ok"}]}
        ),
        live_check=maybe({"report_md": "saw hello", "shots": ["evidence/a.png"]}),
        skills_loaded=rng.choice([[], ["build-backend"]]),
        lesson=maybe(
            {"id": "l", "skill": "s", "mistake": "m", "rule": "r", "evidence": "e", "state": "drafted"}
        ),
        ship=maybe({"commit": "abc"}),
        stages=rng.choice([[], [{"stage": "plan", "started": 1.0, "ended": None}]]),
        extra=rng.choice([{}, {"future_key": [1, {"a": None}]}]),
    )


@pytest.mark.parametrize("seed", range(150))
def test_round_trip_property(tmp_path: Path, seed: int) -> None:
    original = random_state(random.Random(seed))
    state.save(tmp_path, original)
    assert state.load(tmp_path) == original
    assert RunState.from_dict(json.loads(json.dumps(original.to_dict()))) == original
    validate("state", original.to_dict())


def test_fixture_loads_validates_and_round_trips() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    loaded = RunState.from_dict(raw)
    assert loaded.spec_questions[0].answer == "demo.py"
    assert loaded.to_dict() == raw
    validate("state", loaded.to_dict())


def test_minimal_state_gets_defaults() -> None:
    loaded = RunState.from_dict({"task_id": "abcd1234", "stage": "plan", "assignee": "claude"})
    assert loaded.cost_usd == 0.0
    assert loaded.session_id is None
    assert loaded.open_questions() == []
    assert loaded.to_dict()["last_tag"] is None


def test_open_questions() -> None:
    qs = [SpecQuestion("Q1", "a"), SpecQuestion("Q2", "b", answer="x")]
    assert [q.id for q in RunState("t", "spec_wait", spec_questions=qs).open_questions()] == ["Q1"]


def test_unknown_keys_survive_a_cycle(tmp_path: Path) -> None:
    raw = {"task_id": "abcd1234", "stage": "plan", "assignee": "claude", "newer": {"x": 1}}
    state.save(tmp_path, RunState.from_dict(raw))
    again = state.load(tmp_path)
    assert again is not None
    assert json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))["newer"] == {"x": 1}


def test_load_missing_is_none(tmp_path: Path) -> None:
    assert state.load(tmp_path / "nope") is None
    assert state.load(tmp_path) is None


GOOD: dict[str, Any] = {"task_id": "abcd1234", "stage": "plan", "assignee": "claude"}


@pytest.mark.parametrize(
    "bad",
    [
        [],
        {"stage": "plan", "assignee": "claude"},
        {**GOOD, "stage": "bogus"},
        {**GOOD, "assignee": 7},
        {**GOOD, "assignee": "robot"},
        {**GOOD, "last_tag": "Z"},
        {**GOOD, "cost_usd": "x"},
        {**GOOD, "spec_questions": ["x"]},
        {**GOOD, "spec_questions": [{"id": "Q1"}]},
        {**GOOD, "sessions": []},
    ],
)
def test_malformed_state_raises(bad: object) -> None:
    with pytest.raises(StateError):
        RunState.from_dict(bad)


def test_unreadable_file_raises(tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(StateError, match="not valid JSON"):
        state.load(tmp_path)


def test_save_leaves_no_tmp_and_replaces(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "abcd1234"
    state.save(target, RunState("abcd1234", "plan"))
    state.save(target, RunState("abcd1234", "implement"))
    assert sorted(p.name for p in target.iterdir()) == [".state.lock", "state.json"]
    loaded = state.load(target)
    assert loaded is not None
    assert loaded.stage == "implement"


def test_concurrent_saves_never_tear(tmp_path: Path) -> None:
    def writer(n: int) -> None:
        for i in range(20):
            state.save(tmp_path, RunState("abcd1234-0", "plan", cost_usd=n, error="x" * (n * 50 + i)))

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(6)]
    for thread in threads:
        thread.start()
    for _ in range(50):
        loaded = state.load(tmp_path)
        assert loaded is None or loaded.task_id == "abcd1234-0"
    for thread in threads:
        thread.join()
    assert state.load(tmp_path) is not None


def test_run_root_env_and_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TODOIMPL_HOME", str(tmp_path))
    assert state.run_root() == tmp_path
    monkeypatch.delenv("TODOIMPL_HOME")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert state.run_root() == tmp_path / ".cache" / "todoImplementer"
    assert state.run_dir(tmp_path, "c59d2588-3") == tmp_path / "c59d2588-3"


def test_load_runs_skips_missing_and_turns_corruption_into_a_failed_run(tmp_path: Path) -> None:
    state.save(state.run_dir(tmp_path, "aaaaaaaa"), RunState("aaaaaaaa", "plan"))
    bad = state.run_dir(tmp_path, "bbbbbbbb")
    bad.mkdir()
    (bad / "state.json").write_text("[]", encoding="utf-8")
    runs = state.load_runs(tmp_path, ["aaaaaaaa", "bbbbbbbb", "cccccccc"])
    assert set(runs) == {"aaaaaaaa", "bbbbbbbb"}
    assert runs["bbbbbbbb"].stage == "failed"
    assert "not a JSON object" in (runs["bbbbbbbb"].error or "")

from pathlib import Path

import pytest
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, wait_stage
from todoimpl.runner import checks


def test_capped_defaults_to_the_home_script(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    assert checks.capped() == str(world.bin / "capped.sh")
    monkeypatch.delenv("TODOIMPL_CAPPED")
    assert checks.capped() == str(world.home / ".claude" / "scripts" / "capped.sh")


def test_discover_finds_done_check_make_test_and_pre_commit(tmp_path: Path) -> None:
    assert checks.discover(tmp_path, None) == []
    (tmp_path / "Makefile").write_text("lint:\n\techo\n", encoding="utf-8")
    assert checks.discover(tmp_path, "test -f x") == [("done_check", "test -f x")]
    (tmp_path / "Makefile").write_text("test: lint\n\techo\n", encoding="utf-8")
    (tmp_path / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    assert checks.discover(tmp_path, None) == [
        ("tests", "make test"),
        ("pre-commit", "pre-commit run --all-files"),
    ]


SENTENCE = "a calibration regression test exists under tests/ (proxy; the real done is the 5-seed run)."


@pytest.mark.parametrize(
    ("done_check", "runs"),
    [
        ("test -f x", True),
        ("cd app && flutter test", True),
        ("FOO=1 make test", True),
        ("(cd app && ls)", True),
        ("scripts/check.sh --fast", True),
        ("./scripts/check.sh", True),
        (SENTENCE, False),
        ("the page loads and shows hi", False),
        ('echo "unclosed', False),
        ("FOO=1", False),
        ("", False),
    ],
)
def test_t1814_a_sentence_done_check_is_not_run(tmp_path: Path, done_check: str, runs: bool) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    assert checks.is_command(done_check, tmp_path) is runs
    assert (("done_check", done_check) in checks.discover(tmp_path, done_check)) is runs


def test_run_check_passes_fails_and_times_out(world: Env, tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    ok = checks.run_check("done_check", "for i in $(seq 1 50); do echo line$i; done", tmp_path, run_dir, 10)
    assert ok.passed
    assert ok.tail.splitlines() == [f"line{i}" for i in range(11, 51)]
    assert (run_dir / ok.log).exists()
    bad = checks.run_check("tests", "echo boom >&2; exit 3", tmp_path, run_dir, 10)
    assert (bad.passed, bad.exit_code, bad.tail) == (False, 3, "boom")
    slow = checks.run_check("slow", "sleep 5", tmp_path, run_dir, 0.3)
    assert slow.exit_code is None
    assert "timed out after 0.3 s" in slow.tail


def test_run_all_writes_one_log_and_evidence(world: Env, tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    results, log = checks.run_all([("a", "echo fine"), ("b", "true")], tmp_path, run_dir, 10)
    assert log.startswith("logs/checks-")
    assert "== a: echo fine -> 0" in (run_dir / log).read_text(encoding="utf-8")
    rec = checks.record(results, log, 7.0)
    assert rec == {
        "passed": True,
        "ran_at": 7.0,
        "log": log,
        "results": [
            {"command": "echo fine", "exit": 0, "tail": "fine"},
            {"command": "true", "exit": 0, "tail": ""},
        ],
    }
    _, empty = checks.run_all([], tmp_path, run_dir, 10)
    assert (run_dir / empty).read_text(encoding="utf-8") == "no checks found\n"
    slow = checks.run_check("slow", "sleep 5", tmp_path, run_dir, 0.2)
    assert checks.record([slow], log, 1.0)["results"][0]["exit"] == -1
    assert not checks.record([slow], log, 1.0)["passed"]


def test_t1814_a_sentence_done_check_reaches_the_gate_unrun(world: Env) -> None:
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check=SENTENCE)
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        assert st.checks is not None
        assert all(r["name"] != "done_check" for r in st.checks["results"])
        assert checks.SENTENCE_NOTE in world.calls()[0]["prompt"]
        feed = (world.root / CARD / "events.jsonl").read_text(encoding="utf-8")
        assert "done_check not run" in feed
    finally:
        sched.close()

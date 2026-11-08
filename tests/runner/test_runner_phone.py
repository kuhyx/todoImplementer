import json
from pathlib import Path

import pytest
from phonefakes import READY, SERIAL, adb_calls, fake_adb
from runnerfakes import Env
from todoimpl.board.state import RunState
from todoimpl.runner import phone
from todoimpl.runner.stream import TurnResult


def st(**extra: object) -> RunState:
    return RunState(task_id="abcd1234-0", stage="implement", extra=dict(extra))


def stage_ready(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "phone_ready.json").write_text(json.dumps(READY), encoding="utf-8")


@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("done\n\nA: phone: plug in the Pixel", "plug in the Pixel"),
        ("**A:** phone: bold tag", "bold tag"),
        ("A: PHONE:   spaced  ", "spaced"),
        ("A: phone: first\nA: phone: last", "last"),
        ("A: please run X", None),
        ("D: done", None),
        ("a note: A: phone: mid-line", None),
    ],
)
def test_t1500_phone_line_reads_the_last_phone_tag(text: str, line: str | None) -> None:
    assert phone.phone_line(text) == line


def test_t1501_phone_tag_marks_the_run_waiting_and_rests_on_a(tmp_path: Path) -> None:
    run, res = st(), TurnResult(text="x\n\nA: phone: plug in", tag="A")
    run.last_tag = "A"
    stage_ready(tmp_path)
    phone.after_turn(run, tmp_path, res)
    assert run.extra["waiting_phone"] == {**READY, "note": "plug in"}
    assert (res.tag, run.last_tag) == ("A", "A")


def test_t1502_a_staged_file_holds_the_run_even_when_the_turn_says_done(tmp_path: Path) -> None:
    run, res = st(), TurnResult(text="all good\n\nD: done", tag="D")
    run.last_tag = "D"
    stage_ready(tmp_path)
    phone.after_turn(run, tmp_path, res)
    assert run.extra["waiting_phone"] == READY
    assert (res.tag, run.last_tag) == ("A", "A")


def test_phone_tag_without_a_file_still_waits(tmp_path: Path) -> None:
    run, res = st(), TurnResult(text="A: phone: plug in", tag="A")
    phone.after_turn(run, tmp_path, res)
    assert run.extra["waiting_phone"] == {"note": "plug in"}


def test_unreadable_file_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "phone_ready.json").write_text("[1]", encoding="utf-8")
    run, res = st(), TurnResult(text="D: done", tag="D")
    phone.after_turn(run, tmp_path, res)
    assert "waiting_phone" not in run.extra
    assert res.tag == "D"


def test_t1503_a_question_is_never_hidden_by_the_phone(tmp_path: Path) -> None:
    run, res = st(waiting_phone={"x": 1}), TurnResult(text="Q: which one?", tag="Q")
    stage_ready(tmp_path)
    phone.after_turn(run, tmp_path, res)
    assert "waiting_phone" not in run.extra
    assert res.tag == "Q"


def test_t1504_a_plain_turn_drops_a_stale_waiting_phone(tmp_path: Path) -> None:
    run, res = st(waiting_phone={"x": 1}), TurnResult(text="D: done", tag="D")
    phone.after_turn(run, tmp_path, res)
    assert "waiting_phone" not in run.extra


def test_t1505_a_phone_turn_that_ends_done_clears_the_wait(tmp_path: Path) -> None:
    run, res = st(waiting_phone=READY, phone_attached=True), TurnResult(text="D: done", tag="D")
    stage_ready(tmp_path)  # the stale staged file must not re-arm the wait
    phone.after_turn(run, tmp_path, res)
    assert "waiting_phone" not in run.extra
    assert "phone_attached" not in run.extra
    assert not (tmp_path / "phone_ready.json").exists()


def test_t1506_a_phone_turn_that_loses_the_phone_waits_again(tmp_path: Path) -> None:
    run, res = st(waiting_phone=READY, phone_attached=True), TurnResult(text="A: phone: unplugged", tag="A")
    phone.after_turn(run, tmp_path, res)
    assert run.extra["waiting_phone"] == {**READY, "note": "unplugged", "tried_attached": True}
    assert "phone_attached" not in run.extra


def test_t1507_attached_serials_parse_only_ready_devices(world: Env) -> None:
    base = fake_adb(world, f"{SERIAL} device", "emulator-5554 device", "AAA unauthorized", "BBB offline")
    assert phone.attached_serials("adb") == {SERIAL, "emulator-5554"}
    assert adb_calls(base) == ["devices"]


def test_t1508_adb_trouble_means_no_phone(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    base = fake_adb(world, f"{SERIAL} device")
    (base / "hang").write_text("", encoding="utf-8")
    assert phone.attached_serials("adb", timeout=0.3) == set()
    assert phone.attached_serials("/no/such/adb") == set()
    monkeypatch.setenv("TODOIMPL_ADB", "/no/such/adb")
    assert phone.adb_command() == "/no/such/adb"
    monkeypatch.delenv("TODOIMPL_ADB")
    assert phone.adb_command() == "adb"

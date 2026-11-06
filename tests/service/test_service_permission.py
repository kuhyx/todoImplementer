import pytest
from contract_lib import validate
from servicefakes import Rig
from todoimpl.board.state import load, run_dir
from todoimpl.http.backend import BackendError
from todoimpl.service import permission


def blocked_card(rig: Rig, command: str | None = "echo hi", *, tty: bool = False) -> str:
    tid = rig.note()
    rig.run(
        tid, "failed", error="Blocked Bash x: nope", extra={"permission": {"command": command, "tty": tty}}
    )
    return tid


def test_t1660_the_card_shows_the_command_and_validates_against_the_contract(rig: Rig) -> None:
    tid = blocked_card(rig, "cd /w && sudo pacman -S foo", tty=True)
    board = rig.backend.board()
    validate("board", board)
    detail = rig.backend.task(tid)
    assert detail is not None
    validate("task", detail)
    card = rig.card(tid)
    assert card["needs"] == {
        "kind": "permission",
        "category": "permission",
        "effort": 1,
        "text": "Blocked Bash x: nope",
        "command": "cd /w && sudo pacman -S foo",
    }
    by_id = {a["id"]: a for a in card["actions"]}
    assert by_id["go"]["enabled"] is False
    assert by_id["go"]["reason"] == "needs a terminal: copy it"
    assert by_id["copy-fix"]["value"] == "cd /w && sudo pacman -S foo"
    assert by_id["rerun"]["enabled"] is True


def test_t1661_go_runs_the_command_then_reruns_through_the_scheduler(rig: Rig) -> None:
    tid = blocked_card(rig)
    ran: list[str] = []

    def record(command: str) -> tuple[int, str]:
        ran.append(command)
        return 0, "hi"

    rig.backend.fix_runner = record
    rig.backend.go(tid)
    assert ran == ["echo hi"]
    (call,) = rig.scheduler.calls
    assert call[:2] == ("send", tid)
    assert "kuhy clicked Go: ran `echo hi` (exit 0: hi)" in call[2]
    state = load(run_dir(rig.root, tid))
    assert state is not None
    assert "permission" not in state.extra


def test_t1662_a_failing_command_keeps_the_card_and_says_why(rig: Rig) -> None:
    tid = blocked_card(rig)
    rig.backend.fix_runner = lambda _command: (2, "no such file")
    with pytest.raises(BackendError, match="Go: `echo hi` exited 2: no such file") as err:
        rig.backend.go(tid)
    assert err.value.code == "conflict"
    assert not rig.scheduler.calls


def test_t1663_done_rerun_trusts_kuhy_and_reruns(rig: Rig) -> None:
    tid = blocked_card(rig, "sudo true", tty=True)
    rig.backend.rerun(tid)
    assert "kuhy ran `sudo true` himself" in rig.scheduler.calls[0][2]


def test_t1664_a_card_without_a_command_cannot_go(rig: Rig) -> None:
    tid = blocked_card(rig, None)
    with pytest.raises(BackendError, match="no command") as err:
        rig.backend.go(tid)
    assert err.value.code == "disabled"
    unknown = rig.note(title="other")
    with pytest.raises(BackendError, match="no command"):
        rig.backend.rerun(unknown)


def test_t1665_run_command_captures_output_and_exit_code() -> None:
    assert permission.run_command("echo out; echo err >&2; exit 3") == (3, "out\nerr")
    assert permission.run_command("true") == (0, "")


def test_t1666_run_command_kills_a_command_that_outlives_the_timeout() -> None:
    code, tail = permission.run_command("sleep 30", timeout=0.3)
    assert (code, tail) == (124, "timed out after 0 s")

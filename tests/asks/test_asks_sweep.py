"""The sweep helpers: classify, table, add an ask block through a fake todo client, drop the stray note (C15-C17)."""
# ruff: noqa: PT018, PLC0415, E501

import json
import runpy
from pathlib import Path

import pytest
from todoimpl.asks import sweep

BODY = "intro\n## First\nneed it\n\n## MANUAL WORK REQUIRED: pick colour\nold text\n\n\n## Third\nx\n"
BLOCK = "```ask\nchoice c1: Colour | red | *blue | risk=reversible\n```\n"


class Task:
    def __init__(self, id8: str, body: str) -> None:
        self.id, self.body = id8, body


class Client:
    def __init__(self, body: str = BODY) -> None:
        self.task = Task("abcd1234", body)
        self.updates: list[str] = []

    def get_task(self, id8: str) -> Task:
        assert id8 == "abcd1234"
        return self.task

    def update_task(self, id8: str, **fields: str) -> Task:
        self.task.body = fields["body"]
        self.updates.append(fields["body"])
        return self.task

    def list_tasks(self, *, full: bool = False) -> list[Task]:
        assert full
        return [self.task]


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("the note has no Needs: line saying what", "unclear"),
        ("kuhy: sign in to Google", "credential"),
        ("kuhy `! textgate approve` for captions", "command"),
        ("kuhy: haptic felt on the phone", "physical"),
        ("kuhy: narrow vs scoped disable", "decision"),
        ("whatever", "unclear"),
    ],
)
def test_classify(text: str, kind: str) -> None:
    assert sweep.classify(text) == kind


def test_table_and_add_ask_land_in_the_right_section() -> None:
    assert sweep.table([("a-0", "choice", "x")]).splitlines()[2] == "| a-0 | choice | x |"
    client = Client()
    line = sweep.add_ask(client, "abcd1234-1", BLOCK, now=0)  # type: ignore[arg-type]
    assert line.startswith("sweep: ask block added to abcd1234-1")
    assert "old text\n\n```ask\nchoice c1" in client.task.body
    assert client.task.body.index("```ask") < client.task.body.index("## Third")
    sweep.add_ask(client, "abcd1234-2", BLOCK, now=0)  # type: ignore[arg-type]
    assert client.task.body.rstrip().endswith("```")


def test_add_ask_refuses_a_bad_block_or_section() -> None:
    with pytest.raises(ValueError, match="not a valid"):
        sweep.add_ask(Client(), "abcd1234-1", "nope")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not found"):
        sweep.add_ask(Client(), "abcd1234-9", BLOCK)  # type: ignore[arg-type]


def test_drop_note_removes_it_and_logs(tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text(json.dumps({"stage": "implement", "notes": ["stray", "keep"]}))
    assert sweep.drop_note(tmp_path, "stray")
    assert json.loads((tmp_path / "state.json").read_text())["notes"] == ["keep"]
    assert json.loads((tmp_path / "asks.json").read_text())["log"] == ["stray itch note closed"]
    assert not sweep.drop_note(tmp_path, "stray")


def test_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TODOIMPL_HOME", str(tmp_path))
    run = tmp_path / "abcd1234-1"
    run.mkdir()
    (run / "state.json").write_text(json.dumps({"notes": ["stray"]}))
    assert sweep.main(["drop-note", "abcd1234-1", "stray"]) == 0
    assert sweep.main(["drop-note", "abcd1234-1", "stray"]) == 1
    block = tmp_path / "b.md"
    block.write_text(BLOCK)
    client = Client()
    assert sweep.main(["add", "abcd1234-1", str(block)], client) == 0  # type: ignore[arg-type]
    assert "ask block added" in json.loads((run / "asks.json").read_text())["log"][-1]
    other = tmp_path / "wxyz9999-0"
    other.mkdir()
    assert sweep.main(["add", "abcd1234-1", str(block), "--log", "wxyz9999-0"], client) == 0  # type: ignore[arg-type]
    assert "ask block added" in json.loads((other / "asks.json").read_text())["log"][-1]
    client.task.body = "## MANUAL WORK REQUIRED: x\n" + BLOCK + "\n## MANUAL WORK REQUIRED: done\n"
    client.task.body = client.task.body.replace(
        "## MANUAL WORK REQUIRED: done", "## [x] MANUAL WORK REQUIRED: y"
    )
    assert sweep.main(["report"], client) == 0  # type: ignore[arg-type]
    out = capsys.readouterr().out
    assert "| abcd1234-0 | choice |" in out and "y" not in out.splitlines()[-1]


def test_cli_builds_the_real_client_for_report(monkeypatch: pytest.MonkeyPatch) -> None:
    from todoimpl.todo_mcp import client as mod

    monkeypatch.setattr(mod.TodoClient, "from_env", classmethod(lambda _cls: Client()))
    assert sweep.main(["report"]) == 0


def test_module_main(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sys.argv", ["sweep", "drop-note", "zzzzzzzz-0", "x"])
    monkeypatch.setenv("TODOIMPL_HOME", str(tmp_path))
    (tmp_path / "zzzzzzzz-0").mkdir()
    (tmp_path / "zzzzzzzz-0" / "state.json").write_text("{}")
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("todoimpl.asks.sweep", run_name="__main__")
    assert exc.value.code == 1

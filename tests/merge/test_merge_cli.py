"""The CLI and the umbrella creator: same code path as the click, a shim in place of the todo CLI."""

import os
import stat
from pathlib import Path

import pytest
from mergefakes import Rig
from todoimpl.merge import __main__ as cli
from todoimpl.merge import umbrella
from todoimpl.merge.apply import MergeError
from todoimpl.todo_mcp.client import TodoClient

REPO = "kuhyx/a"


@pytest.fixture(autouse=True)
def _wire(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(TodoClient, "from_env", classmethod(lambda _cls, _env=None: rig.client))
    monkeypatch.setattr(cli, "create_umbrella", rig.create_umbrella)


def test_cli_merges_sections_of_one_repo(rig: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    ids = rig.sections(REPO, [("A", ""), ("B", ""), ("C", "")])
    assert cli.main(["--group", f"{ids[0]},{ids[1]}", "--title", "AB"]) == 0
    assert rig.open_titles(REPO) == ["C", "AB"]
    assert "(repo); removed 2:" in capsys.readouterr().out


def test_cli_rerun_after_a_full_merge_finds_nothing_left_to_name(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = rig.sections(REPO, [("A", ""), ("B", "")])
    args = ["--group", ",".join(ids), "--title", "AB"]
    assert cli.main(args) == 0
    capsys.readouterr()
    assert cli.main(args) == 1  # the sections are gone: the ids name nothing
    assert "no such section" in capsys.readouterr().err
    assert rig.open_titles(REPO) == ["AB"]


def test_cli_plain_ids_work_for_single_section_notes_and_umbrellas(rig: Rig) -> None:
    one = rig.fake.seed("kuhyx/one", "Make one text-free (textgate-rework)", "b")
    two = rig.fake.seed("kuhyx/two", "Make two text-free (textgate-rework)", "b")
    assert cli.main(["--group", f"{one[:8]},{two[:8]}", "--title", "All"]) == 0
    assert rig.umbrellas[0].startswith("# All\nUmbrella: per-repo\nTier: cheap\n- [ ] kuhyx/one (")
    assert rig.fake.store.notes[one].status == "done"


def test_cli_dry_run_prints_and_changes_nothing(rig: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    ids = rig.sections(REPO, [("A", "x"), ("B", "y")])
    other = rig.sections("kuhyx/b", [("C", "z")])
    assert cli.main(["--group", ",".join(ids), "--title", "AB", "--dry-run"]) == 0
    assert "### " in capsys.readouterr().out
    assert cli.main(["--group", f"{ids[0]},{other[0]}", "--title", "AB", "--dry-run"]) == 0
    assert capsys.readouterr().out.startswith("# AB\nUmbrella: per-repo")
    assert rig.open_titles(REPO) == ["A", "B"]
    assert rig.umbrellas == []


@pytest.mark.parametrize(
    ("group", "message"),
    [
        ("{many}", "has 2 sections"),
        ("{one}-9", "no such section"),
        ("{one}-x", "no such section"),
        ("ffffffff", "merge:"),
        ("{one}", "at least two"),
    ],
)
def test_cli_refuses_bad_input(
    rig: Rig, capsys: pytest.CaptureFixture[str], group: str, message: str
) -> None:
    ids = rig.sections(REPO, [("A", ""), ("B", "")])
    single = rig.fake.seed("kuhyx/s", "S", "")
    arg = group.format(many=ids[0][:8], one=single[:8])
    assert cli.main(["--group", arg, "--title", "T"]) == 1
    assert message in capsys.readouterr().err


def make_cli(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_umbrella_creator_runs_the_todo_cli_and_reads_the_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "args"
    shim = tmp_path / "note"
    make_cli(shim, f'printf "%s\\n" "$@" > {log}\necho warm\necho 0123abcd-0000-4000-8000-000000000000')
    monkeypatch.setenv("TODOIMPL_TODO_NOTE", str(shim))
    assert umbrella.create_umbrella("# T\nbody") == "0123abcd-0000-4000-8000-000000000000"
    assert log.read_text().splitlines() == ["--text", "# T", "body", "--by", "claude"]


def test_umbrella_creator_default_is_dart_in_the_todo_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TODOIMPL_TODO_NOTE", raising=False)
    monkeypatch.setenv("TODOIMPL_TODO_APP", "/somewhere")
    assert umbrella.note_command() == (["dart", "run", "bin/todo_note.dart"], Path("/somewhere"))
    monkeypatch.delenv("TODOIMPL_TODO_APP")
    assert umbrella.note_command()[1] == Path.home() / "src" / "todo"


@pytest.mark.parametrize(
    "body",
    ["echo not an id", "echo oops >&2; exit 3", "exit 0", "sleep 5"],
)
def test_umbrella_creator_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    shim = tmp_path / "note"
    make_cli(shim, body)
    monkeypatch.setenv("TODOIMPL_TODO_NOTE", str(shim))
    monkeypatch.setattr(umbrella, "TIMEOUT_S", 0.3)
    with pytest.raises(MergeError) as err:
        umbrella.create_umbrella("# T")
    assert err.value.code == "upstream_unavailable"


def test_umbrella_creator_without_the_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TODOIMPL_TODO_NOTE", str(tmp_path / "missing"))
    with pytest.raises(MergeError, match="cannot run"):
        umbrella.create_umbrella("# T")
    assert os.environ["TODOIMPL_TODO_NOTE"]

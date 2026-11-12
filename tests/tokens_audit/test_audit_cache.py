"""T1997: a warm per-file cache re-parses nothing and changes no number."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import audit_notes_fixtures as fx
import pytest
from todoimpl.tokens.audit import __main__ as cli
from todoimpl.tokens.audit import notes, parse

if TYPE_CHECKING:
    from collections.abc import Callable

UNTIL = "4102444800"  # fixed so two runs share one window
# 2026-10-10: between the two records of the cut-window test.
MID_OCT = "1791583200"


@pytest.fixture
def parsed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Count every JSONL line parsed by the audit (window parser and note scanner)."""
    seen: list[str] = []

    def spy(real: Callable[[str], Any]) -> Callable[[str], Any]:
        def wrapper(line: str) -> Any:
            seen.append(line)
            return real(line)

        return wrapper

    monkeypatch.setattr(parse, "_load_line", spy(parse._load_line))
    monkeypatch.setattr(parse, "load_line", spy(parse.load_line))
    return seen


def _world(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    fx.transcript(
        root,
        "s1",
        [fx.prompt(fx.BODY_A), fx.tool_use("Bash", {"command": "ls"}, msg="m1"), fx.tool_result("ok")],
    )
    fx.subagent(root, "s1", "a1", [fx.tool_use("Read", {"file_path": "/x"}, msg="m2")])
    fx.transcript(
        root, "s2", [fx.prompt("something else"), fx.tool_use("Bash", {"command": "pwd"}, msg="m3")]
    )
    fx.backlog(notes.backlog_path_for(Path.home()))
    return root


def _snapshot(
    root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *window: str,
) -> dict[str, Any]:
    argv = ["--root", str(root), "--out", str(tmp_path / "out"), "--no-write", "--json", "--recommend"]
    assert cli.main([*argv, "--until", UNTIL, *(window or ("--days", "36500"))]) == 0
    loaded: dict[str, Any] = json.loads(capsys.readouterr().out)
    loaded.pop("generated")  # wall-clock stamp of the run itself
    return loaded


def test_t1997_warm_run_parses_nothing_and_matches_cold(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    parsed: list[str],
) -> None:
    root = _world(tmp_path)
    cold = _snapshot(root, tmp_path, capsys)
    assert parsed
    parsed.clear()
    warm = _snapshot(root, tmp_path, capsys)
    assert parsed == []
    assert warm == cold
    assert cold["metrics"]["note_linked_usd_share"] == 0.6667


def test_t1997_changed_file_is_reparsed_alone(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    parsed: list[str],
) -> None:
    root = _world(tmp_path)
    cold = _snapshot(root, tmp_path, capsys)
    parsed.clear()
    path = root / "proj" / "s2.jsonl"
    extra = json.dumps(fx.tool_use("Bash", {"command": "id"}, msg="m9", usd_tokens=5000))
    path.write_text(path.read_text(encoding="utf-8") + "\n" + extra, encoding="utf-8")
    changed = _snapshot(root, tmp_path, capsys)
    assert 0 < len(parsed) <= 6  # only s2: once for the window, once for the note scan
    assert changed["turns"] == cold["turns"] + 1
    parsed.clear()
    assert _snapshot(root, tmp_path, capsys) == changed
    assert parsed == []


def test_t1997_window_cutting_a_file_is_not_served_from_cache(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "projects"
    early = fx.tool_use("Bash", {"command": "a"}, stamp="2026-10-01T00:00:00Z", msg="e1")
    late = fx.tool_use("Bash", {"command": "b"}, stamp="2026-10-20T00:00:00Z", msg="e2", usd_tokens=4000)
    fx.transcript(root, "s1", [early, late])
    whole = _snapshot(root, tmp_path, capsys)
    assert whole["turns"] == 2
    cut = _snapshot(root, tmp_path, capsys, "--since", MID_OCT)
    assert cut["turns"] == 1
    assert _snapshot(root, tmp_path, capsys, "--since", MID_OCT) == cut

"""Durable writes: fault injection (rename fails, power cut before fsync) and an audit of every writer."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from todoimpl import atomic
from todoimpl.runner import files

SERVER = Path(__file__).resolve().parents[1] / "server" / "todoimpl"
HAND_ROLLED = re.compile(r"\btmp\.replace\(|os\.replace\(|\.with_suffix\([^)]*tmp")
ALLOWED = {"atomic.py", "state.py"}  # state.py also holds a flock around its own fsynced rename


def test_t1901_the_new_file_is_synced_before_the_rename_and_the_directory_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd: int) -> None:
        order.append("fsync")
        real_fsync(fd)

    def replace(src: Path, dst: Path) -> None:
        order.append("replace")
        real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)
    atomic.write_text(tmp_path / "state.json", "{}\n")
    assert order == ["fsync", "replace", "fsync"]


def test_t1901_a_failed_rename_keeps_the_old_file_whole_and_leaves_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "state.json"
    atomic.write_text(target, '{"old": true}\n')

    def boom(_a: object, _b: object) -> None:
        raise OSError

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):  # noqa: PT011 - the injected fault
        atomic.write_text(target, '{"new": true}\n')
    assert json.loads(target.read_text(encoding="utf-8")) == {"old": True}
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_t1901_a_power_cut_before_the_fsync_never_shows_a_torn_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "round.json"
    files.write_json(target, {"n": 1})

    def cut(_fd: int) -> None:
        raise KeyboardInterrupt  # the machine died mid-write: nothing after this ran

    monkeypatch.setattr(os, "fsync", cut)
    with pytest.raises(KeyboardInterrupt):
        files.write_json(target, {"n": 2})
    assert files.read_json(target) == {"n": 1}


def test_append_line_adds_the_newline_and_syncs(tmp_path: Path) -> None:
    log = tmp_path / "sub" / "free-issues.jsonl"
    atomic.append_line(log, "one")
    atomic.append_line(log, "two\n")
    assert log.read_text(encoding="utf-8") == "one\ntwo\n"


def test_t1901_no_module_renames_a_temp_file_by_hand() -> None:
    offenders = [
        str(p.relative_to(SERVER))
        for p in SERVER.rglob("*.py")
        if p.name not in ALLOWED and HAND_ROLLED.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], "use todoimpl.atomic.write_text"

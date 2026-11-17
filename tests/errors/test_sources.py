"""Configured error sources, their hooks and the default kartka entry."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from errfakes import kartka_entry, rec, shim, write_kartka, write_report
from todoimpl.errors import sources
from todoimpl.errors.adapters import SourceError
from todoimpl.errors.sources import Source

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIMPL_ERROR_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("TODOIMPL_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def settings(tmp_path: Path, value: object) -> None:
    (tmp_path / "settings.json").write_text(json.dumps({"error_sources": value}), encoding="utf-8")


def test_the_default_is_kartka_under_the_state_root(tmp_path: Path) -> None:
    (found,) = sources.configured()
    assert (found.app, found.repo, found.adapter) == ("kartka", "kuhyx/kartka", "kartka")
    assert found.path == tmp_path / "state" / "kartka-errors" / "state.json"
    assert found.resolve[0] == str(tmp_path / "home" / "src" / "kartka" / "tools" / "errors" / "run.sh")
    assert found.resolve[1:] == ("resolve", "{signature}")
    assert found.build[:3] == ("git", "-C", "{repo_dir}")


def test_the_state_root_defaults_to_home_local_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("TODOIMPL_ERROR_STATE_ROOT")
    assert sources.state_base() == tmp_path / "home" / ".local" / "state"


def test_settings_replace_the_default_and_bad_entries_are_skipped(tmp_path: Path) -> None:
    good = {
        "app": "tutor",
        "repo": "kuhyx/tutor",
        "adapter": "contract",
        "path": "~/t.json",
        "resolve": ["x"],
    }
    settings(
        tmp_path, [good, {"app": "no-repo"}, "text", {**good, "adapter": "weird"}, {**good, "resolve": 5}]
    )
    (found,) = sources.configured()
    assert found.app == "tutor"
    assert found.path == tmp_path / "home" / "t.json"
    assert found.resolve == ("x",)
    assert found.build == ()


def test_a_non_list_setting_falls_back_to_the_default(tmp_path: Path) -> None:
    settings(tmp_path, "nope")
    assert [s.app for s in sources.configured()] == ["kartka"]


def test_an_empty_list_turns_the_default_off(tmp_path: Path) -> None:
    settings(tmp_path, [])
    assert sources.configured() == []


def test_every_json_file_in_app_errors_is_a_contract_source(tmp_path: Path) -> None:
    settings(tmp_path, [])
    write_report(tmp_path / "state" / "app-errors" / "tutor.json", rec(app="tutor", repo="kuhyx/tutor"))
    (tmp_path / "state" / "app-errors" / "notes.txt").write_text("x", encoding="utf-8")
    (found,) = sources.configured()
    assert (found.app, found.adapter, found.resolve) == ("tutor", "contract", ())


def test_a_configured_file_is_not_listed_twice(tmp_path: Path) -> None:
    path = write_report(
        tmp_path / "state" / "app-errors" / "tutor.json", rec(app="tutor", repo="kuhyx/tutor")
    )
    own = {"app": "tutor", "repo": "kuhyx/tutor", "adapter": "contract", "path": str(path), "resolve": ["r"]}
    settings(tmp_path, [own])
    (found,) = sources.configured()
    assert found.resolve == ("r",)


def test_records_come_from_each_source_and_a_broken_one_is_skipped(tmp_path: Path) -> None:
    k = write_kartka(tmp_path / "k.json", kartka_entry("aaa"))
    c = write_report(tmp_path / "c.json", rec(app="tutor", repo="kuhyx/tutor", signature="bbb"))
    bad = tmp_path / "bad.json"
    bad.write_text("nope", encoding="utf-8")
    found = [
        Source("kartka", "kuhyx/kartka", "kartka", k),
        Source("x", "kuhyx/x", "contract", bad),
        Source("tutor", "", "contract", c),
    ]
    got = sources.records(found)
    assert [(s.app, r.signature) for s, r in got] == [("kartka", "aaa"), ("tutor", "bbb")]


def test_read_raises_for_a_broken_file(tmp_path: Path) -> None:
    with pytest.raises(SourceError):
        sources.read(Source("x", "kuhyx/x", "contract", tmp_path / "none.json"))


def test_resolve_runs_the_hook_with_the_signature(tmp_path: Path) -> None:
    log = tmp_path / "log"
    hook = shim(tmp_path / "run.sh", log)
    src = Source(
        "kartka", "kuhyx/kartka", "kartka", tmp_path / "s.json", (str(hook), "resolve", "{signature}")
    )
    assert sources.resolve(src, "02b0d43d9f") is True
    assert log.read_text(encoding="utf-8").strip() == "resolve 02b0d43d9f"


def test_resolve_fails_on_exit_code_missing_tool_or_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hook = shim(tmp_path / "run.sh", tmp_path / "log", code=3)
    assert sources.resolve(Source("a", "o/a", "kartka", tmp_path, (str(hook),)), "s") is False
    assert sources.resolve(Source("a", "o/a", "kartka", tmp_path, (str(tmp_path / "none"),)), "s") is False
    monkeypatch.setattr(sources, "HOOK_TIMEOUT", 0.2)
    slow = tmp_path / "slow.sh"
    slow.write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
    slow.chmod(0o755)
    assert sources.resolve(Source("a", "o/a", "kartka", tmp_path, (str(slow),)), "s") is False


def test_a_source_with_no_resolve_hook_has_nothing_to_call(tmp_path: Path) -> None:
    assert sources.resolve(Source("a", "o/a", "contract", tmp_path), "s") is True


def test_build_of_reads_the_number_the_hook_prints(tmp_path: Path) -> None:
    hook = shim(tmp_path / "b.sh", tmp_path / "log", out="87")
    src = Source("a", "o/a", "kartka", tmp_path, (), (str(hook), "{repo_dir}", "{commit}"))
    assert sources.build_of(src, tmp_path / "repo", "abc") == 87
    assert (tmp_path / "log").read_text(encoding="utf-8").strip() == f"{tmp_path / 'repo'} abc"


def test_build_of_is_zero_when_unknown(tmp_path: Path) -> None:
    assert sources.build_of(Source("a", "o/a", "kartka", tmp_path), tmp_path, "abc") == 0
    word = shim(tmp_path / "w.sh", tmp_path / "log", out="not a number")
    assert sources.build_of(Source("a", "o/a", "kartka", tmp_path, (), (str(word),)), tmp_path, "abc") == 0
    bad = shim(tmp_path / "f.sh", tmp_path / "log", code=1, out="9")
    assert sources.build_of(Source("a", "o/a", "kartka", tmp_path, (), (str(bad),)), tmp_path, "abc") == 0


def test_a_hook_template_with_an_unknown_placeholder_is_a_failed_hook(tmp_path: Path) -> None:
    assert sources.resolve(Source("a", "o/a", "kartka", tmp_path, ("echo", "{repo_dir}")), "s") is False
    assert (
        sources.build_of(Source("a", "o/a", "kartka", tmp_path, (), ("echo", "{nope}")), tmp_path, "c") == 0
    )

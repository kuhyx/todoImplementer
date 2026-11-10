"""One-shot Haiku calls (classify, lesson drafts): a narrow claude, its answer parsed, its usage recorded."""

from __future__ import annotations

import json
import stat
from typing import TYPE_CHECKING, Any

import pytest
from todoimpl.runner import oneshot

if TYPE_CHECKING:
    from pathlib import Path

RESULT: dict[str, Any] = {
    "type": "result", "is_error": False, "result": "hello", "total_cost_usd": 0.0005,
    "usage": {"input_tokens": 3, "output_tokens": 7, "cache_read_input_tokens": 3600,
              "cache_creation_input_tokens": 12},
}  # fmt: skip
SHIM = """#!/usr/bin/env python3
import json, os, sys, time
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps({"argv": sys.argv[1:], "stdin": sys.stdin.read(), "cwd": os.getcwd()}) + "\\n")
time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
sys.stdout.write(os.environ["FAKE_STDOUT"])
sys.exit(int(os.environ.get("FAKE_RC", "0")))
"""


class BoomError(Exception):
    """The caller's own error type."""


@pytest.fixture
def shim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    claude = tmp_path / "claude"
    claude.write_text(SHIM)
    claude.chmod(claude.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("TODOIMPL_CLAUDE", str(claude))
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "calls.log"))
    monkeypatch.setenv("FAKE_STDOUT", json.dumps(RESULT))
    return tmp_path / "calls.log"


def call(root: Path, timeout: float = 5.0) -> str:
    return oneshot.run(
        "the prompt", model="haiku", kind="classify", root=root, timeout=timeout, error=BoomError
    )


def test_t1894_a_one_shot_loads_none_of_kuhys_setup(shim: Path, tmp_path: Path) -> None:
    assert call(tmp_path / "root") == "hello"
    seen = json.loads(shim.read_text().splitlines()[0])
    argv = seen["argv"]
    assert argv[:5] == ["-p", "--model", "haiku", "--output-format", "json"]
    assert "--strict-mcp-config" in argv
    assert "--disable-slash-commands" in argv
    assert argv[argv.index("--setting-sources") + 1] == ""  # no user, project or local settings: no hooks
    assert argv[argv.index("--tools") + 1] == ""  # no tools
    assert argv[argv.index("--effort") + 1] == "low"
    assert seen["stdin"] == "the prompt"
    assert seen["cwd"] == str(tmp_path / "root" / "oneshot")  # no project CLAUDE.md is found from there


def test_t1894_the_json_array_of_events_claude_2_1_prints_is_read_too(
    shim: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = [{"type": "system"}, {"type": "assistant"}, RESULT]
    monkeypatch.setenv("FAKE_STDOUT", json.dumps(events))
    assert call(tmp_path) == "hello"
    assert shim.exists()


def test_t1894_the_cost_and_tokens_of_a_call_are_recorded_in_the_root_ledger(
    shim: Path, tmp_path: Path
) -> None:
    call(tmp_path)
    (row,) = [json.loads(x) for x in (tmp_path / oneshot.LEDGER).read_text().splitlines()]
    assert shim.exists()
    assert row["kind"] == "classify"
    assert row["model"] == "haiku"
    assert row["cost_usd"] == 0.0005
    assert (row["input_tokens"], row["output_tokens"]) == (3, 7)
    assert (row["cache_read_tokens"], row["cache_write_tokens"]) == (3600, 12)
    assert row["at"] > 0
    call(tmp_path)
    assert len((tmp_path / oneshot.LEDGER).read_text().splitlines()) == 2


def test_t1894_spend_sums_the_ledger_and_skips_bad_lines(tmp_path: Path) -> None:
    assert oneshot.spend(tmp_path, since=0.0) == 0.0
    ledger = tmp_path / oneshot.LEDGER
    ledger.write_text('{"at": 10, "cost_usd": 0.5}\nnot json\n{"at": 20, "cost_usd": 0.25}\n[1]\n{"at": 5}\n')
    assert oneshot.spend(tmp_path, since=0.0) == 0.75
    assert oneshot.spend(tmp_path, since=15.0) == 0.25


@pytest.mark.parametrize(
    ("stdout", "rc", "why"),
    [
        ("oops", "1", "exit 1"),
        ("not json", "0", "non-JSON"),
        (json.dumps({**RESULT, "is_error": True}), "0", "no text"),
        ('{"result": 5}', "0", "no text"),
        ("[1, 2]", "0", "no text"),
        ("[]", "0", "no text"),
    ],
)
def test_failures_raise_the_callers_error(  # noqa: PLR0917
    shim: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stdout: str, rc: str, why: str
) -> None:
    monkeypatch.setenv("FAKE_STDOUT", stdout)
    monkeypatch.setenv("FAKE_RC", rc)
    with pytest.raises(BoomError, match=why):
        call(tmp_path)
    assert shim.exists()


def test_a_slow_or_missing_claude_raises_the_callers_error(
    shim: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_SLEEP", "5")
    with pytest.raises(BoomError, match="timed out"):
        call(tmp_path, timeout=0.3)
    monkeypatch.setenv("TODOIMPL_CLAUDE", str(tmp_path / "missing"))
    with pytest.raises(BoomError, match="cannot run claude"):
        call(tmp_path)

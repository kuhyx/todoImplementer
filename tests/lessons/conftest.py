"""Hermetic fixtures for the lessons tests: temp HOME, a fake `claude` on PATH, a fake skill_lesson.py."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

FAKE_CLAUDE = """#!/usr/bin/env python3
import json, os, sys, time
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps({"argv": sys.argv[1:], "stdin": sys.stdin.read(),
                          "auto": os.environ.get("CLAUDE_AUTO_CONTINUE")}) + "\\n")
time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
sys.stdout.write(os.environ["FAKE_STDOUT"])
sys.exit(int(os.environ.get("FAKE_RC", "0")))
"""

FAKE_SKILL_LESSON = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
print(os.environ.get("FAKE_MSG", "recorded L1"))
sys.exit(int(os.environ.get("FAKE_RC", "0")))
"""


@dataclass
class Env:
    """Handles on the fake environment."""

    home: Path
    run_dir: Path
    log: Path
    shim_dir: Path

    def calls(self) -> list[Any]:
        """Every logged invocation, in order."""
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []


def _executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    home = tmp_path / "home"
    shim_dir = tmp_path / "bin"
    log = tmp_path / "calls.log"
    for skill in ("build-backend", "build-web-ui", "grilling"):
        (home / ".claude/skills" / skill).mkdir(parents=True)
        (home / ".claude/skills" / skill / "SKILL.md").write_text("x")
    (home / ".claude/skills/build-empty").mkdir()
    _executable(shim_dir / "claude", FAKE_CLAUDE)
    _executable(home / ".claude/scripts/skill_lesson.py", FAKE_SKILL_LESSON)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("PROGRAM_SKILLS_DIR", raising=False)
    monkeypatch.setenv("PATH", f"{shim_dir}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_LOG", str(log))
    run_dir = tmp_path / "run" / "abcd1234-0"
    run_dir.mkdir(parents=True)
    return Env(home=home, run_dir=run_dir, log=log, shim_dir=shim_dir)


@pytest.fixture
def claude_says(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Make the fake `claude` print a `--output-format json` envelope carrying `text`."""

    def _say(text: str, **envelope: Any) -> None:
        body = {"type": "result", "subtype": "success", "is_error": False, "result": text, **envelope}
        monkeypatch.setenv("FAKE_STDOUT", json.dumps(body))

    return _say


@pytest.fixture(scope="session")
def lesson_validator() -> Any:
    """Return a validator for common.schema.json#/$defs/lesson."""
    contracts = Path(__file__).resolve().parents[2] / "contracts"
    registry: Registry = Registry()
    for f in contracts.glob("*.schema.json"):
        data = json.loads(f.read_text())
        registry = registry.with_resource(data["$id"], Resource.from_contents(data))
    return Draft202012Validator(
        {"$ref": "https://todoimplementer.local/contracts/common.schema.json#/$defs/lesson"},
        registry=registry,
    )

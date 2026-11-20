"""Heavy gate steps take the build lock before capped.sh starts its 60 s scope (T2417).

`capped.sh uv run pytest` started the 60 s scope, then queued on the build lock inside it: a test shard
waited 53 s and was killed after 5 s of work. The lock-taking tool (uv, pnpm) must come first on the line.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(("var", "tool"), [("TESTCAP", "uv run"), ("WEBCAP", "pnpm")])
def test_t2417_the_lock_taking_tool_runs_before_the_capped_scope(var: str, tool: str) -> None:
    line = subprocess.run(
        ["make", "-s", "-C", str(ROOT), "--eval", "print-%: ; @echo $($*)", f"print-{var}", "CAP=CAPPED"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert line.startswith(tool)
    assert line.index(tool) < line.index("CAPPED")


@pytest.mark.parametrize("target", ["test", "test-shard", "web-lint", "web-test"])
def test_t2417_the_heavy_steps_use_the_lock_first_wrappers(target: str) -> None:
    recipe = (ROOT / "Makefile").read_text().split(f"\n{target}:\n", 1)[1].split("\n\n", 1)[0]
    assert "$(TESTCAP)" in recipe or "$(WEBCAP)" in recipe
    assert "$(CAP) pnpm" not in recipe

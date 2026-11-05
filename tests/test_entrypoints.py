"""The `python scripts/x.py` entry points exit with main()'s code; the package has a version."""

import runpy
import subprocess
from pathlib import Path

import pytest
from todoimpl import version

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


@pytest.mark.parametrize("script", ["check_lines.py", "check_regressions.py"])
def test_script_runs_as_main(script: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    monkeypatch.setattr("sys.argv", [script, str(tmp_path)])
    with pytest.raises(SystemExit) as stop:
        runpy.run_path(str(SCRIPTS / script), run_name="__main__")
    assert stop.value.code == 0


def test_check_private_runs_as_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    deny = tmp_path / "deny.txt"
    deny.write_text("nevermatches\n")
    monkeypatch.setenv("TODOIMPL_PRIVATE_DENYLIST", str(deny))
    monkeypatch.setattr("sys.argv", ["check_private.py", "--root", str(root)])
    with pytest.raises(SystemExit) as stop:
        runpy.run_path(str(SCRIPTS / "check_private.py"), run_name="__main__")
    assert stop.value.code == 0


def test_version_is_semver() -> None:
    assert len(version.__version__.split(".")) == 3

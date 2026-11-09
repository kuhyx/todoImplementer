"""run.sh: deploy (scripts/deploy.sh: tools, build, unit, restart, /version check), then open the page."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from deploy_testkit import DEPLOY, Env, Stubber

if TYPE_CHECKING:
    from collections.abc import Callable

RUN = DEPLOY.parent / "run.sh"
HEAD = subprocess.run(
    ["git", "-C", str(DEPLOY.parent), "rev-parse", "--short", "HEAD"],
    capture_output=True,
    text=True,
    check=True,
).stdout.strip()
VERSION_OK = f'echo \'{{"build": "{HEAD}", "version": "0.1.0"}}\''  # what /version says
URL = "http://127.0.0.1:8786/"
FAST_WAIT = {"RUN_WAIT_TRIES": "3", "RUN_WAIT_INTERVAL": "0.01"}
# Direct systemctl stub body: the preview unit is active unless PREVIEW_RC says otherwise.
SYSTEMCTL = 'case "$*" in *is-active*) exit "${PREVIEW_RC:-0}";; esac'


def _stubs(stub: Stubber, *, pnpm: str = "", curl: str = VERSION_OK) -> None:
    for tool in ("uv", "xdg-open"):
        stub(tool)
    stub("pnpm", pnpm)
    stub("systemctl", SYSTEMCTL)
    stub("journalctl", 'echo "JOURNAL-TAIL-LINE"')
    stub("curl", curl)


# (log-line test, tag) pairs; unmatched lines (is-active probes) are skipped.
_TAGS: tuple[tuple[Callable[[str], bool], str], ...] = (
    (lambda line: line.startswith("uv python install"), "python"),
    (lambda line: line.startswith("uv sync"), "sync"),
    (lambda line: line.startswith("pnpm") and "install" in line, "pnpm-install"),
    (lambda line: line.startswith("pnpm") and "build" in line, "build"),
    (lambda line: "daemon-reload" in line, "reload"),
    (lambda line: " stop " in line, "stop-preview"),
    (lambda line: " enable " in line, "enable"),
    (lambda line: " restart " in line, "restart"),
    (lambda line: line.startswith("curl"), "curl"),
    (lambda line: line.startswith("xdg-open"), "open"),
)


def _opened(env: Env) -> str:
    """Return the call log once the detached xdg-open has logged (run.sh does not wait for it)."""
    deadline = time.monotonic() + 3
    while "xdg-open" not in env.calls and time.monotonic() < deadline:
        time.sleep(0.02)
    return env.calls


def _kinds(calls: str) -> list[str]:
    """Reduce the call log to one short tag per step, in order."""
    return [tag for line in calls.splitlines() for test, tag in _TAGS if test(line)]


def test_run_happy_path_order(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _stubs(stub)
    done = env.run("bash", str(RUN), **FAST_WAIT)
    assert done.returncode == 0, done.stderr
    _opened(env)
    assert _kinds(env.calls) == [
        "python",
        "sync",
        "pnpm-install",
        "build",
        "reload",
        "stop-preview",
        "enable",
        "restart",
        "curl",
        "open",
    ]
    assert "uv python install 3.15.2" in env.calls
    assert "uv sync --frozen" in env.calls
    assert "pnpm --dir" in env.calls
    assert "--frozen-lockfile" in env.calls
    assert "systemctl --user stop todoimplementer-preview.service" in env.calls
    assert "systemctl --user enable --now todoimplementer.service" in env.calls
    assert "systemctl --user restart todoimplementer.service" in env.calls
    assert "curl" in env.calls
    assert "http://127.0.0.1:8786/version" in env.calls
    assert _opened(env).splitlines()[-1] == f"xdg-open {URL}"
    unit = env.home / ".config" / "systemd" / "user" / "todoimplementer.service"
    assert unit.read_text() == (DEPLOY / "todoimplementer.service").read_text()
    assert "pacman" not in env.calls


def test_run_skips_stop_when_preview_inactive(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _stubs(stub)
    done = env.run("bash", str(RUN), PREVIEW_RC="3", **FAST_WAIT)
    assert done.returncode == 0, done.stderr
    assert " stop " not in env.calls
    assert _opened(env).splitlines()[-1] == f"xdg-open {URL}"


def _system_bin_without(tmp_path: Path, *missing: str) -> Path:
    """Mirror /usr/bin as symlinks minus `missing`, so the test, not the host, decides which tools exist."""
    sysbin = tmp_path / "sysbin"
    sysbin.mkdir()
    for real in Path("/usr/bin").iterdir():
        if real.name not in missing:
            (sysbin / real.name).symlink_to(real)
    return sysbin


def test_t1858_run_installs_only_the_missing_tool(box: tuple[Env, Stubber], tmp_path: Path) -> None:
    env, stub = box
    _stubs(stub)
    (tmp_path / "bin" / "uv").unlink()
    # The sudo stub plays pacman: it drops a uv stub into the bin dir, like a real install would.
    uv_stub = '#!/bin/bash\\necho "uv $*" >> "$STUB_LOG"\\n'
    stub(
        "sudo",
        f"printf '{uv_stub}' > '{tmp_path}/bin/uv'; chmod +x '{tmp_path}/bin/uv'",
    )
    sysbin = _system_bin_without(tmp_path, "uv")
    done = env.run("bash", str(RUN), PATH=f"{tmp_path}/bin:{sysbin}", **FAST_WAIT)
    assert done.returncode == 0, done.stderr
    assert "sudo pacman -S --needed --noconfirm uv\n" in env.calls
    assert env.calls.count("pacman") == 1
    assert _opened(env).splitlines()[-1] == f"xdg-open {URL}"


def test_t1859_run_finds_uv_in_the_per_user_bin_dir(box: tuple[Env, Stubber], tmp_path: Path) -> None:
    env, stub = box
    _stubs(stub)
    (tmp_path / "bin" / "uv").unlink()
    user_bin = env.home / ".local" / "bin"
    user_bin.mkdir(parents=True)
    uv = user_bin / "uv"
    uv.write_text('#!/bin/bash\necho "uv $*" >> "$STUB_LOG"\n')
    uv.chmod(0o755)
    stub("sudo")
    sysbin = _system_bin_without(tmp_path, "uv")
    # What systemd-run gives a script: no ~/.local/bin on PATH.
    done = env.run("bash", str(RUN), PATH=f"{tmp_path}/bin:{sysbin}", **FAST_WAIT)
    assert done.returncode == 0, done.stderr
    assert "pacman" not in env.calls
    assert "uv sync --frozen" in env.calls


def test_run_build_failure_aborts_before_restart(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _stubs(stub, pnpm='case "$*" in *build*) exit 1;; esac')
    done = env.run("bash", str(RUN), **FAST_WAIT)
    assert done.returncode != 0
    assert "restart" not in env.calls
    assert "xdg-open" not in env.calls


def test_run_never_ready_prints_journal_and_does_not_open(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _stubs(stub, curl="exit 22")
    done = env.run("bash", str(RUN), **FAST_WAIT)
    assert done.returncode == 1
    assert "JOURNAL-TAIL-LINE" in done.stdout + done.stderr
    assert "journalctl --user -u todoimplementer.service -n 20" in env.calls
    assert "xdg-open" not in env.calls


def test_t502_run_returns_while_the_browser_keeps_running(box: tuple[Env, Stubber]) -> None:
    """The opened browser inherits no pipe: run.sh returns at once and its output carries no browser log."""
    env, stub = box
    _stubs(stub)
    stub("xdg-open", "echo BROWSER-LOG; echo BROWSER-ERR >&2; (sleep 15) &")
    start = time.monotonic()
    done = env.run("bash", str(RUN), **FAST_WAIT)
    assert done.returncode == 0, done.stderr
    assert time.monotonic() - start < 5
    assert "BROWSER-" not in done.stdout + done.stderr
    assert _opened(env).splitlines()[-1] == f"xdg-open {URL}"

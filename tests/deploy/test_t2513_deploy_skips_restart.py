"""scripts/deploy.sh restarts the board only when something the running server holds changed (T2513).

On 2026-11-22 15:43-15:44 a Ship relaunched `bash scripts/deploy.sh` three times for one HEAD and every run
restarted the board, cutting the Ship that ran it. A deploy of the HEAD the board already serves, with the
same unit files installed, now verifies /version without a restart; `--restart` or DEPLOY_RESTART=1 forces it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from deploy_testkit import DEPLOY, Env, Stubber
from test_deploy_run import FAST_WAIT, HEAD, VERSION_OK

if TYPE_CHECKING:
    from pathlib import Path

DEPLOY_SH = DEPLOY.parent / "scripts" / "deploy.sh"
UNITS = ("todoimplementer.service", "todoimpl.slice", "todoimpl-.slice.d/50-card-cap.conf")
# The board unit is active, the preview unit is not (unless PREVIEW_RC=0 makes it active too).
SYSTEMCTL = (
    'case "$*" in *is-active*preview*) exit "${PREVIEW_RC:-3}";; *is-active*) exit "${BOARD_RC:-0}";; esac'
)


def _installed(env: Env) -> Path:
    """Install the repo's unit files as a previous deploy left them; return the unit dir."""
    unit_dir = env.home / ".config" / "systemd" / "user"
    for name in UNITS:
        target = unit_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((DEPLOY / name).read_text())
    return unit_dir


def _live_board(box: tuple[Env, Stubber]) -> Env:
    env, stub = box
    for tool in ("uv", "pnpm", "claude"):
        stub(tool)
    stub("systemctl", SYSTEMCTL)
    stub("journalctl", 'echo "JOURNAL-TAIL-LINE"')
    stub("curl", VERSION_OK)
    _installed(env)
    return env


def test_t2513_a_second_deploy_of_the_served_head_does_not_restart_the_board(
    box: tuple[Env, Stubber],
) -> None:
    env = _live_board(box)
    done = env.run("bash", str(DEPLOY_SH), **FAST_WAIT)
    assert done.returncode == 0, done.stderr
    assert " restart " not in env.calls
    assert "daemon-reload" not in env.calls
    assert "systemctl --user enable todoimplementer.service" in env.calls  # still survives a reboot (T1906)
    assert "http://127.0.0.1:8786/version" in env.calls  # /version is still checked
    assert f"already serves {HEAD}" in done.stdout
    assert f"serving build {HEAD}" in done.stdout
    assert "uv sync --frozen" in env.calls  # tools and build still run


def test_t2513_restart_flag_or_env_forces_a_restart(box: tuple[Env, Stubber]) -> None:
    env = _live_board(box)
    done = env.run("bash", str(DEPLOY_SH), "--restart", **FAST_WAIT)
    assert done.returncode == 0, done.stderr
    assert "systemctl --user restart todoimplementer.service" in env.calls
    env.log.write_text("")
    again = env.run("bash", str(DEPLOY_SH), DEPLOY_RESTART="1", **FAST_WAIT)
    assert again.returncode == 0, again.stderr
    assert "systemctl --user restart todoimplementer.service" in env.calls


def test_t2513_a_changed_unit_file_restarts(box: tuple[Env, Stubber]) -> None:
    env = _live_board(box)
    (env.home / ".config" / "systemd" / "user" / "todoimpl.slice").write_text("[Slice]\n")
    done = env.run("bash", str(DEPLOY_SH), **FAST_WAIT)
    assert done.returncode == 0, done.stderr
    assert "systemctl --user daemon-reload" in env.calls
    assert "systemctl --user restart todoimplementer.service" in env.calls
    assert (env.home / ".config" / "systemd" / "user" / "todoimpl.slice").read_text().startswith("#")


def test_t2513_an_active_preview_unit_or_a_stopped_board_restarts(box: tuple[Env, Stubber]) -> None:
    """The preview unit answers on the same port; a HEAD it serves is not the board serving it."""
    env = _live_board(box)
    done = env.run("bash", str(DEPLOY_SH), PREVIEW_RC="0", **FAST_WAIT)
    assert done.returncode == 0, done.stderr
    assert "systemctl --user stop todoimplementer-preview.service" in env.calls
    assert "systemctl --user restart todoimplementer.service" in env.calls
    env.log.write_text("")
    again = env.run("bash", str(DEPLOY_SH), BOARD_RC="3", **FAST_WAIT)
    assert again.returncode == 0, again.stderr
    assert "systemctl --user restart todoimplementer.service" in env.calls


def test_t2513_an_old_build_restarts(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _live_board(box)
    old = 'n=$(cat "$HOME/curl.n" 2>/dev/null || echo 0); echo $((n + 1)) > "$HOME/curl.n"; '
    stub("curl", old + '[ "$n" -ge 1 ] || { echo \'{"build": "0000000"}\'; exit 0; }; ' + VERSION_OK)
    done = env.run("bash", str(DEPLOY_SH), **FAST_WAIT)
    assert done.returncode == 0, done.stderr
    assert "systemctl --user restart todoimplementer.service" in env.calls


def test_t2513_an_unknown_argument_is_refused_before_anything_runs(box: tuple[Env, Stubber]) -> None:
    env = _live_board(box)
    done = env.run("bash", str(DEPLOY_SH), "--force", **FAST_WAIT)
    assert done.returncode == 1
    assert "usage: scripts/deploy.sh [--restart]" in done.stderr
    assert env.calls == ""

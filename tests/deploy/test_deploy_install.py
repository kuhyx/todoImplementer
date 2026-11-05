"""install.sh: build, install, restart, prove the live build id."""

from __future__ import annotations

import shutil
from pathlib import Path

from deploy_testkit import DEPLOY, Env, Stubber


def _systemctl(stub: Stubber, active: str = "inactive") -> None:
    stub(
        "systemctl",
        f'case "$*" in *is-active*) echo {active};; *ExecMainStartTimestamp*) echo "Thu 12:00";; esac',
    )


def _install_stubs(stub: Stubber, version: str = "abc1234", listener: str = "") -> None:
    _systemctl(stub)
    stub("pnpm")
    stub("curl", f"printf '%s' '{version}'")
    stub("ss", f"printf '%s' '{listener}'")
    stub("systemd-analyze")
    stub("loginctl", "echo yes")


def test_install_full_run(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _install_stubs(stub)
    done = env.run("bash", str(DEPLOY / "install.sh"))
    assert done.returncode == 0, done.stderr
    assert "live: todoimplementer.service build abc1234" in done.stdout
    unit = env.home / ".config" / "systemd" / "user" / "todoimplementer.service"
    assert unit.read_text() == (DEPLOY / "todoimplementer.service").read_text()
    order = [line for line in env.calls.splitlines() if line.startswith(("pnpm", "systemctl"))]
    assert [c.split()[1] for c in order if c.startswith("pnpm")] == ["--dir", "--dir"]
    flat = " | ".join(order)
    assert flat.index("daemon-reload") < flat.index("enable") < flat.index("restart")
    assert "pnpm --dir " in env.calls
    assert "build" in env.calls


def test_install_skip_build_and_linger_warning(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _install_stubs(stub)
    stub("loginctl", "echo no")
    done = env.run("bash", str(DEPLOY / "install.sh"), "--skip-build")
    assert done.returncode == 0
    assert "linger is off" in done.stderr
    assert "pnpm" not in env.calls


def test_install_dry_run_changes_nothing(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _install_stubs(stub)
    done = env.run("bash", str(DEPLOY / "install.sh"), "--dry-run")
    assert done.returncode == 0
    assert "dry run ok" in done.stdout
    assert not (env.home / ".config").exists()
    assert "pnpm" not in env.calls
    assert "restart" not in env.calls


def test_install_dry_run_fails_when_unit_does_not_verify(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _install_stubs(stub)
    stub("systemd-analyze", "exit 1")
    done = env.run("bash", str(DEPLOY / "install.sh"), "--dry-run")
    assert done.returncode == 1
    assert "does not verify" in done.stderr


def test_install_refuses_foreign_listener(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _install_stubs(stub, listener="LISTEN 0 5 127.0.0.1:8786 users:((nginx))")
    done = env.run("bash", str(DEPLOY / "install.sh"))
    assert done.returncode == 1
    assert "held by something" in done.stderr
    assert "pnpm" not in env.calls


def test_install_accepts_own_active_listener(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _install_stubs(stub, listener="LISTEN 127.0.0.1:8786")
    _systemctl(stub, active="active")
    assert env.run("bash", str(DEPLOY / "install.sh"), "--skip-build").returncode == 0


def test_install_fails_on_stale_build(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _install_stubs(stub, version="old9999")
    done = env.run("bash", str(DEPLOY / "install.sh"), "--skip-build")
    assert done.returncode == 1
    assert "!= expected" in done.stderr


def test_install_needs_a_commit(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _install_stubs(stub)
    stub("git", "exit 1")
    done = env.run("bash", str(DEPLOY / "install.sh"), TODOIMPL_BUILD_ID="")
    assert done.returncode == 1
    assert "no git commit" in done.stderr


def test_install_usage_and_missing_tool(box: tuple[Env, Stubber], tmp_path: Path) -> None:
    env, stub = box
    _install_stubs(stub)
    assert env.run("bash", str(DEPLOY / "install.sh"), "--bogus").returncode == 1
    empty = tmp_path / "empty"
    empty.mkdir()
    for tool in ("bash", "dirname", "git", "python3"):
        (empty / tool).symlink_to(shutil.which(tool) or "/bin/true")
    done = env.run("/usr/bin/env", "bash", str(DEPLOY / "install.sh"), PATH=str(empty))
    assert done.returncode == 1
    assert "is required" in done.stderr


def test_install_with_token_ingest_swaps_timers(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _install_stubs(stub)
    done = env.run("bash", str(DEPLOY / "install.sh"), "--skip-build", "--with-token-ingest")
    assert done.returncode == 0, done.stderr
    units = env.home / ".config" / "systemd" / "user"
    assert (units / "token-ingest.timer").exists()
    assert (units / "token-ingest.service").exists()
    assert "disable --now token-dashboard-ingest.timer" in env.calls
    assert "enable --now token-ingest.timer" in env.calls


def test_install_dry_run_with_token_ingest_changes_nothing(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _install_stubs(stub)
    done = env.run("bash", str(DEPLOY / "install.sh"), "--dry-run", "--with-token-ingest")
    assert done.returncode == 0, done.stderr
    assert "disable token-dashboard-ingest.timer" in done.stdout
    assert "disable" not in env.calls
    assert not (env.home / ".config").exists()

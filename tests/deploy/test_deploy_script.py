"""scripts/deploy.sh: restart the live unit and prove the new code is what answers, without a browser."""

from __future__ import annotations

from deploy_testkit import DEPLOY, Env, Stubber
from test_deploy_run import FAST_WAIT, HEAD, SYSTEMCTL, VERSION_OK

DEPLOY_SH = DEPLOY.parent / "scripts" / "deploy.sh"


def _stubs(stub: Stubber, curl: str = VERSION_OK) -> None:
    for tool in ("uv", "pnpm", "xdg-open"):
        stub(tool)
    stub("systemctl", SYSTEMCTL)
    stub("journalctl", 'echo "JOURNAL-TAIL-LINE"')
    stub("curl", curl)


def test_deploy_succeeds_when_version_reports_head_and_opens_no_browser(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _stubs(stub)
    done = env.run("bash", str(DEPLOY_SH), **FAST_WAIT)
    assert done.returncode == 0, done.stderr
    assert f"serving build {HEAD}" in done.stdout
    assert "systemctl --user restart todoimplementer.service" in env.calls
    assert "xdg-open" not in env.calls


def test_t1817_deploy_compares_version_with_head_not_with_the_web_build_id(box: tuple[Env, Stubber]) -> None:
    """TODOIMPL_BUILD_ID only stamps the web build; /version says HEAD, so a stale server must not pass."""
    env, stub = box
    _stubs(stub, curl='echo \'{"build": "abc1234", "version": "0.1.0"}\'')  # the testkit's TODOIMPL_BUILD_ID
    done = env.run("bash", str(DEPLOY_SH), **FAST_WAIT)
    assert done.returncode == 1
    assert f"serves build abc1234, expected {HEAD}" in done.stderr
    assert "JOURNAL-TAIL-LINE" in done.stdout + done.stderr


def test_deploy_reports_a_server_that_never_answers(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _stubs(stub, curl="exit 22")
    done = env.run("bash", str(DEPLOY_SH), **FAST_WAIT)
    assert done.returncode == 1
    assert "never answered /version" in done.stderr


def test_t1857_deploy_creates_the_sdk_venv_once_with_the_exact_pin(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _stubs(stub)
    venv = env.home / "sdk-venv"
    done = env.run("bash", str(DEPLOY_SH), TODOIMPL_SDK_VENV=str(venv), **FAST_WAIT)
    assert done.returncode == 0, done.stderr
    assert f"uv venv --quiet --python 3.15.2 {venv}" in env.calls
    install = f"uv pip install --quiet --python {venv}/bin/python -r"
    assert install in env.calls
    assert "requirements-sdk.txt" in env.calls
    pinned = (DEPLOY / "requirements-sdk.txt").read_text()
    assert "claude-agent-sdk==" in pinned


def test_t1857_an_existing_sdk_venv_is_kept_and_only_the_pin_is_applied(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _stubs(stub)
    venv = env.home / "sdk-venv"
    (venv / "bin").mkdir(parents=True)
    python = venv / "bin" / "python"
    python.write_text("#!/bin/sh\n")
    python.chmod(0o755)
    done = env.run("bash", str(DEPLOY_SH), TODOIMPL_SDK_VENV=str(venv), **FAST_WAIT)
    assert done.returncode == 0, done.stderr
    assert "uv venv" not in env.calls
    assert "uv pip install" in env.calls


def test_t1906_deploy_turns_lingering_on_so_the_board_survives_a_reboot_without_a_login(
    box: tuple[Env, Stubber],
) -> None:
    env, stub = box
    _stubs(stub)
    done = env.run("bash", str(DEPLOY_SH), LINGER="no", **FAST_WAIT)
    assert done.returncode == 0, done.stderr
    assert "loginctl enable-linger" in env.calls
    assert "lingering on" in done.stdout


def test_deploy_leaves_lingering_alone_when_it_is_already_on(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _stubs(stub)
    done = env.run("bash", str(DEPLOY_SH), **FAST_WAIT)
    assert done.returncode == 0, done.stderr
    assert "enable-linger" not in env.calls


def test_deploy_fails_when_lingering_cannot_be_turned_on(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    _stubs(stub)
    stub("loginctl", 'case "$*" in *show-user*) echo no;; esac')  # enable-linger does nothing
    done = env.run("bash", str(DEPLOY_SH), **FAST_WAIT)
    assert done.returncode == 1
    assert "lingering" in done.stderr

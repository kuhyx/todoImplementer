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

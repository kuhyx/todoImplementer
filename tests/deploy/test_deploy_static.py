"""Static checks: syntax, shellcheck, unit/manifest/snippet contract, publish patch."""

from __future__ import annotations

import json
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from deploy_testkit import DEPLOY, Env, Stubber

SCRIPTS = [
    DEPLOY.parent / "run.sh",
    DEPLOY.parent / "scripts" / "deploy.sh",
    DEPLOY / "lib.sh",
    DEPLOY / "install.sh",
    DEPLOY / "oauth2-proxy" / "run.sh",
    DEPLOY / "google_oauth_handoff.sh",
]
REDIRECT = "https://agents.kuhy.duckdns.org/oauth2/callback"


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_shell_syntax_and_strict_mode(script: Path) -> None:
    assert subprocess.run(["bash", "-n", str(script)], check=False).returncode == 0
    if script.name != "lib.sh":
        assert "set -euo pipefail" in script.read_text()
        assert script.stat().st_mode & stat.S_IXUSR
    assert len(script.read_text().splitlines()) <= 250


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck missing")
def test_shellcheck_clean() -> None:
    done = subprocess.run(
        ["shellcheck", "-x", *map(str, SCRIPTS)], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stdout


def test_unit_file_contract() -> None:
    text = (DEPLOY / "todoimplementer.service").read_text()
    assert (
        "ExecStart=%h/.local/bin/uv run --python 3.15 --project %h/src/todoImplementer"
        " python -m todoimpl.http.main" in text
    )
    for line in (
        "Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin\n",
        "Environment=TODOIMPL_CLAUDE=%h/.local/bin/claude",
        "Restart=on-failure",
        "KillMode=process",
        "WantedBy=default.target",
    ):
        assert line in text


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="systemd-analyze missing")
def test_unit_file_verifies() -> None:
    done = subprocess.run(
        ["systemd-analyze", "--user", "verify", str(DEPLOY / "todoimplementer.service")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "Unknown" not in done.stderr, done.stderr
    assert "Invalid" not in done.stderr, done.stderr


def test_manifest_matches_control_panel_shape() -> None:
    data = json.loads((DEPLOY / "control-panel-todoimplementer.json").read_text())
    assert data["id"] == "todoimplementer"
    assert set(data) <= {"id", "title", "category", "units", "containers", "dashboards", "docs"}
    assert data["units"][0] == {
        "name": "todoimplementer.service",
        "scope": "user",
        "kind": "service",
        "why_it_matters": data["units"][0]["why_it_matters"],
    }
    assert {d["url"] for d in data["dashboards"]} == {
        "http://127.0.0.1:8786/",
        "http://127.0.0.1:8786/usage/",
        "https://agents.kuhy.duckdns.org/",
    }


def test_caddy_snippet_gates_everything() -> None:
    text = (DEPLOY / "caddy" / "agents.kuhy.duckdns.org.caddy").read_text()
    for needle in (
        "agents.kuhy.duckdns.org {",
        "handle /oauth2/* {",
        "forward_auth 127.0.0.1:4186",
        "uri /oauth2/auth",
        "reverse_proxy 127.0.0.1:8786",
        "flush_interval -1",
    ):
        assert needle in text
    # The app is only reachable inside the forward_auth handle block.
    assert text.index("forward_auth") < text.index("reverse_proxy 127.0.0.1:8786")


UPSTREAM = Path.home() / "src/testsAndMisc/linux_configuration/features/publish_caddy_site.sh"
PATCH = DEPLOY / "patches" / "publish_caddy_site.patch"


@pytest.fixture
def patched_site_script(tmp_path: Path) -> Path:
    """Return a scratch copy of the upstream script with the patch applied (upstream untouched)."""
    if not UPSTREAM.exists():
        pytest.skip("upstream publish_caddy_site.sh not present")
    feat = tmp_path / "linux" / "features"
    feat.mkdir(parents=True)
    shutil.copy(UPSTREAM, feat / "publish_caddy_site.sh")
    done = subprocess.run(
        ["patch", "-p1", "-i", str(PATCH)],
        cwd=tmp_path / "linux",
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        pytest.skip(f"upstream changed since the patch was cut: {done.stdout}")
    return feat / "publish_caddy_site.sh"


def test_patch_renders_the_reference_snippet(
    box: tuple[Env, Stubber], patched_site_script: Path, tmp_path: Path
) -> None:
    env, stub = box
    stub("docker")
    sites = tmp_path / "sites"
    sites.mkdir()
    done = env.run(
        "bash",
        str(patched_site_script),
        "agents",
        "8786",
        "--forward-auth",
        "127.0.0.1:4186",
        SITES_DIR=str(sites),
    )
    assert done.returncode == 0, done.stderr
    rendered = (sites / "agents.kuhy.duckdns.org.caddy").read_text().splitlines()[1:]
    reference = (DEPLOY / "caddy" / "agents.kuhy.duckdns.org.caddy").read_text().splitlines()[2:]
    assert rendered == reference
    assert "exec gitea-caddy caddy reload" in env.calls


def test_patch_keeps_old_usage_and_rejects_bad_input(
    box: tuple[Env, Stubber], patched_site_script: Path, tmp_path: Path
) -> None:
    env, stub = box
    stub("docker")
    sites = tmp_path / "sites"
    sites.mkdir()
    base = ["bash", str(patched_site_script), "dice", "8123"]
    plain = env.run(*base, "--dry-run", SITES_DIR=str(sites))
    assert plain.returncode == 0
    assert "dry run ok" in plain.stdout
    assert not list(sites.iterdir())
    for bad in (["--forward-auth"], ["--forward-auth", "a b"], ["--nope"]):
        assert env.run(*base, *bad, SITES_DIR=str(sites)).returncode == 1

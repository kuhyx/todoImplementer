"""[T2613] A free-model implement turn pushed its own commit to main before any Claude check (live C1)."""

import subprocess
from pathlib import Path

import pytest
from todoimpl.prompts import PromptContext, build, standing
from todoimpl.runner import freeroute, srcwall
from todoimpl.runner.claude import Invocation


def _git(*args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=False)


@pytest.fixture
def free_inv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Invocation:
    monkeypatch.setenv("TODOIMPL_FREE_CLAUDE", "/x/claude-free")
    monkeypatch.setattr(srcwall, "wrap", lambda _w, _s: ([], ""))
    grant = standing.GRANT.format(base="main", run_dir=tmp_path)
    return freeroute.build("implement", f"Do the part.\n{grant}\nEnd with D:.", tmp_path / "wt")


def test_t2613_free_prompt_drops_the_landing_grant(free_inv: Invocation) -> None:
    prompt = free_inv.argv[free_inv.argv.index("-p") + 1]
    assert "standing permission to land" not in prompt
    assert "push origin HEAD" not in prompt
    assert freeroute.NO_LAND in prompt
    assert "Do the part." in prompt
    assert "Never write test or probe notes" in prompt  # the rest of the standing text stays


@pytest.mark.parametrize(
    "form", [("push", "origin", "HEAD:main"), ("-C", "{wt}", "push", "origin", "HEAD:main")]
)
def test_t2613_free_turn_env_refuses_every_push(
    tmp_path: Path, free_inv: Invocation, form: tuple[str, ...]
) -> None:
    origin, wt = tmp_path / "origin.git", tmp_path / "wt"
    _git("init", "-q", "--bare", "-b", "main", str(origin), cwd=tmp_path)
    _git("clone", "-q", str(origin), str(wt), cwd=tmp_path)
    (wt / "a").write_text("a", encoding="utf-8")
    _git("add", "a", cwd=wt)
    _git("commit", "-qm", "a", cwd=wt)
    done = _git(*(part.format(wt=wt) for part in form), cwd=wt, env=free_inv.env)
    assert done.returncode != 0
    assert _git("rev-parse", "-q", "--verify", "refs/heads/main", cwd=origin).returncode != 0
    assert (
        _git("push", "origin", "HEAD:main", cwd=wt).returncode == 0
    )  # the same push outside a free turn works


@pytest.mark.parametrize("stage", ["plan", "implement", "live_check"])
def test_t2613_real_free_prompts_hold_no_landing_text(
    stage: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TODOIMPL_FREE_CLAUDE", "/x/claude-free")
    monkeypatch.setattr(srcwall, "wrap", lambda _w, _s: ([], ""))
    ctx = PromptContext(title="t", body="", repo="r", worktree=tmp_path / "wt", run_dir=tmp_path)
    inv = freeroute.build(stage, build(stage, ctx), tmp_path / "wt")
    prompt = inv.argv[inv.argv.index("-p") + 1]
    for text in ("permission to land", "push origin", "land the work yourself", "landed the same way"):
        assert text not in prompt, (stage, text)
    assert freeroute.NO_LAND in prompt


def test_t2613_ssh_url_pushes_are_refused_too() -> None:
    env = freeroute.no_push({})
    pairs = {
        (env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"])
        for i in range(int(env["GIT_CONFIG_COUNT"]))
    }
    refused = f"url.{freeroute.REFUSED}.pushInsteadOf"
    assert {
        (refused, "ssh://git@github.com/"),
        (refused, "git@github.com:"),
        (refused, "https://github.com/"),
    } <= pairs

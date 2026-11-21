"""T2466: each run's deploy gets its own capped.sh pool, not one shared `todoimpldeploy` 4 GiB pool."""

from pathlib import Path

import pytest
from runnerfakes import Env, make_repo
from todoimpl.runner import checks, deployhost, worktree

PROBE = 'echo "POOL=[${CLAUDE_CODE_SESSION_ID-}]"'


def test_t2466_deploys_of_two_runs_use_two_pools(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    make_repo(world)
    wt = worktree.add(world.src / "demo", world.root, "aaaa1111-0").path
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "server-own-session")
    a = deployhost.run(world.root / "aaaa1111-0", wt, PROBE)
    b = deployhost.run(world.root / "bbbb2222-0", wt, PROBE)
    assert "POOL=[todoimpl" + "aaaa11110]" in a["tail"]
    assert "POOL=[todoimpl" + "bbbb22220]" in b["tail"]


def test_t2466_the_pool_is_the_run_not_its_deploy_dir(tmp_path: Path) -> None:
    run = tmp_path / "7808ee0a-22"
    assert checks.pool_env(run / deployhost.DEPLOY_DIR) == checks.pool_env(run)

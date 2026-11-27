"""Which checkouts the no-limit runner visits, and the commands it reads from their CLAUDE.md."""

from __future__ import annotations

from pathlib import Path

from nolimitfakes import kuhy_repo
from runnerfakes import Env, make_repo, sh
from todoimpl.nolimit import repos


def test_t2540_only_real_checkouts_of_kuhys_repos(world: Env) -> None:
    kuhy_repo(world, "beta", test="make test")
    kuhy_repo(world, "alpha", gate="make fast", test="make test")
    make_repo(world, "local")  # a bare-path origin names no owner
    foreign = make_repo(world, "fork")
    sh(foreign, "git", "remote", "set-url", "origin", "git@github.com:someone/fork.git")
    linked = world.src / "linked"
    sh(world.src / "alpha", "git", "worktree", "add", "-q", str(linked))  # a `.git` file: not a checkout
    (world.src / "plain").mkdir()
    (world.src / "file.txt").write_text("x", encoding="utf-8")
    found = repos.discover(world.src)
    assert [(r.name, r.slug, r.gate) for r in found] == [
        ("alpha", "kuhyx/alpha", "make fast"),
        ("beta", "kuhyx/beta", "make test"),
    ]


def test_discover_without_a_src_root(tmp_path: Path) -> None:
    assert repos.discover(tmp_path / "missing") == []


def test_commands_skip_fences_and_keep_the_first() -> None:
    text = "- test: `one`\n```\n- lint: `fenced`\n```\n- test: `two`\n"
    text += "* Lint: `ruff check`\n- run: ``\n- x: plain\n"
    assert repos.commands_of(text) == {"test": "one", "lint": "ruff check"}


def test_slug_reads_ssh_and_rejects_odd_configs(tmp_path: Path) -> None:
    clone = tmp_path / "c"
    (clone / ".git").mkdir(parents=True)
    assert repos.slug_of(clone) is None  # no config
    config = clone / ".git" / "config"
    config.write_text('[remote "origin"]\n\turl = git@github.com:KuhyX/thing.git\n', encoding="utf-8")
    assert repos.slug_of(clone) == "kuhyx/thing"
    config.write_text("[core]\n\tbare = false\n", encoding="utf-8")
    assert repos.slug_of(clone) is None
    config.write_bytes(b"\xff\xfe")
    assert repos.slug_of(clone) is None


def test_a_repo_without_claude_md_is_read_only(world: Env) -> None:
    path = kuhy_repo(world, "bare")
    (path / "CLAUDE.md").unlink()
    found = repos.load(path)
    assert found is not None
    assert found.commands == {}
    assert found.gate is None

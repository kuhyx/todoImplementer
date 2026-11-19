"""T1987: Ship finds the deploy line when HEAD's CLAUDE.md is a git symlink to another file."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from runnerfakes import sh
from todoimpl.runner import deployline
from todoimpl.runner.files import NeedsYouError

if TYPE_CHECKING:
    from pathlib import Path

DEPLOY = "## Commands\n- deploy: `scripts/deploy.sh`\n"


def _repo(tmp_path: Path, files: dict[str, str], links: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    sh(repo, "git", "init", "-q", "-b", "main")
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    for rel, target in links.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).symlink_to(target)
    sh(repo, "git", "add", "-A")
    sh(repo, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
    return repo


def test_t1987_a_claude_md_symlink_to_agents_md_is_followed(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"AGENTS.md": DEPLOY}, {"CLAUDE.md": "AGENTS.md"})
    assert deployline.command_of(repo, "kuhyx/demo") == "scripts/deploy.sh"


def test_t1987_a_regular_claude_md_still_wins(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"CLAUDE.md": DEPLOY, "AGENTS.md": "- deploy: `other`\n"}, {})
    assert deployline.command_of(repo, None) == "scripts/deploy.sh"


def test_t1987_a_chain_of_links_and_a_subdirectory_target_are_followed(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"docs/real.md": DEPLOY}, {"CLAUDE.md": "docs/mid.md", "docs/mid.md": "real.md"})
    assert deployline.command_of(repo, "kuhyx/demo") == "scripts/deploy.sh"


@pytest.mark.parametrize(
    ("files", "links"),
    [
        ({}, {}),  # no CLAUDE.md at all
        ({"AGENTS.md": DEPLOY}, {"CLAUDE.md": "/etc/AGENTS.md"}),  # absolute target
        ({"AGENTS.md": DEPLOY}, {"CLAUDE.md": "../AGENTS.md"}),  # escapes the repo
        ({"AGENTS.md": DEPLOY}, {"CLAUDE.md": "sub/../../AGENTS.md"}),  # escapes after normalising
        ({}, {"CLAUDE.md": "MISSING.md"}),  # dangling
        ({"d/x": "y"}, {"CLAUDE.md": "d"}),  # points at a directory
        ({}, {"CLAUDE.md": "CLAUDE.md"}),  # loop
        ({"AGENTS.md": "- run: `x`\n"}, {"CLAUDE.md": "AGENTS.md"}),  # target has no deploy line
    ],
)
def test_t1987_unusable_links_still_say_no_deploy_declared(
    tmp_path: Path, files: dict[str, str], links: dict[str, str]
) -> None:
    repo = _repo(tmp_path, files or {"README.md": "x\n"}, links)
    with pytest.raises(NeedsYouError, match=r"declares no deploy: command in CLAUDE\.md"):
        deployline.command_of(repo, "kuhyx/demo")

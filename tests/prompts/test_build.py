"""Golden text per stage plus the rules each prompt must carry."""

from __future__ import annotations

from pathlib import Path

import pytest
from todoimpl.prompts import STAGES, Kind, PromptContext, build
from todoimpl.prompts.kind import HINTS

GOLDEN = Path(__file__).parent / "golden"


@pytest.mark.parametrize("stage", sorted(STAGES))
def test_golden(stage: str, ctx: PromptContext) -> None:
    assert build(stage, ctx) + "\n" == (GOLDEN / f"{stage}.txt").read_text()


@pytest.mark.parametrize("stage", sorted(STAGES))
def test_short(stage: str, ctx: PromptContext) -> None:
    assert len(build(stage, ctx).splitlines()) <= 40


@pytest.mark.parametrize("stage", sorted(STAGES.keys() - {"spec"}))
def test_override_first_after_spec(stage: str, ctx: PromptContext) -> None:
    assert build(stage, ctx).splitlines()[0] == "override"


def test_spec_has_no_override_and_card_format(ctx: PromptContext) -> None:
    text = build("spec", ctx)
    assert "override" not in text.splitlines()
    assert "❓ **Q1** - **<title>**: <body>\n➡️ <your recommended answer>" in text


def test_plan_names_plan_file_and_numbered_criteria(ctx: PromptContext) -> None:
    text = build("plan", ctx)
    assert "/run/ab12cd34/plan.md" in text
    assert "`C1.`" in text
    assert "observable behaviour in the live app" in text


@pytest.mark.parametrize("stage", ["implement", "fix", "resume_after_kill", "fresh_after_idle"])
def test_work_stages_forbid_commit_and_push(stage: str, ctx: PromptContext) -> None:
    text = build(stage, ctx)
    assert "Never commit, push or touch main" in text
    assert "capped.sh" in text
    assert "under 60 s" in text


@pytest.mark.parametrize("stage", ["implement", "fix", "resume_after_kill", "fresh_after_idle"])
def test_work_stages_say_how_to_avoid_the_blocks_no_permission_mode_lifts(
    stage: str, ctx: PromptContext
) -> None:
    text = build(stage, ctx)
    assert "no `rm` on a bare variable or a glob after `cd` or `$(...)`: use explicit absolute paths" in text
    assert "no zsh-only expansions like `${(f)...}`" in text
    assert ".pre-commit-config.yaml" in text
    assert "through Bash (python, sed or git apply), not Edit or Write" in text


def test_implement_ends_with_self_check_and_red_first(ctx: PromptContext) -> None:
    text = build("implement", ctx)
    assert "failing check first" in text
    assert "`Cn: done` or `Cn: not done`" in text


def test_live_check_contract(ctx: PromptContext) -> None:
    text = build("live_check", ctx)
    assert "/run/ab12cd34/live_check.md" in text
    assert "/run/ab12cd34/shots/" in text
    assert "- [x] C1: what I did -> what I saw" in text
    assert "Tests or reading code never count. No video." in text


@pytest.mark.parametrize(
    ("marker", "kind"),
    [
        ("package.json", Kind.WEB),
        ("pubspec.yaml", Kind.FLUTTER),
        ("project.godot", Kind.GODOT),
        ("pyproject.toml", Kind.PYTHON),
        ("a.sh", Kind.SHELL),
        ("README.md", Kind.UNKNOWN),
    ],
)
def test_live_check_hint_follows_kind(tmp_path: Path, ctx: PromptContext, marker: str, kind: Kind) -> None:
    (tmp_path / marker).write_text("x")
    text = build("live_check", PromptContext(**{**ctx.__dict__, "worktree": tmp_path}))
    assert f"({kind})" in text
    assert HINTS[kind] in text


def test_fix_truncates_failure_tail(ctx: PromptContext) -> None:
    long = PromptContext(**{**ctx.__dict__, "failure_tail": "OLD" + "x" * 3000 + "NEW"})
    text = build("fix", long)
    assert "NEW" in text
    assert "OLD" not in text


def test_minimal_context_omits_optional_blocks(tmp_path: Path) -> None:
    bare = PromptContext(title="t", body="", repo="r", worktree=tmp_path, run_dir=tmp_path)
    text = build("implement", bare)
    assert "done_check: none" in text
    assert "Spec answers" not in text
    assert "kuhy's notes" not in text
    assert f"Plan: read {tmp_path}/plan.md." in text
    assert "(none)" in build("fresh_after_idle", bare)


def test_unknown_stage_raises(ctx: PromptContext) -> None:
    with pytest.raises(ValueError, match="unknown prompt stage 'review'"):
        build("review", ctx)

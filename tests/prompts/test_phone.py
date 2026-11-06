"""The phone-last prompt lines: emulator first, staged phone_ready.json, then the attached verification."""

from __future__ import annotations

from dataclasses import replace

from todoimpl.prompts import PromptContext, build

READY = {
    "deploy_cmd": "phone_deploy.sh /apps/demo --release --stage install",
    "criteria": ["C3", "C7"],
    "checks": "the toggle survives a restart",
}


def test_t1520_live_check_stages_the_phone_after_the_emulator(ctx: PromptContext) -> None:
    text = build("live_check", ctx)
    assert "emulator_run.sh boot|install <apk>" in text
    assert "/run/ab12cd34/phone_ready.json" in text
    assert "`- [~] Cn: needs phone: <why>`" in text
    assert "`A: phone: <one line>`" in text
    assert "emulator-5554 only" in text


def test_implement_still_builds_the_release_apk(ctx: PromptContext) -> None:
    assert "release APK" in build("implement", ctx)


def test_t1521_attached_live_check_deploys_and_verifies_only_the_staged_criteria(ctx: PromptContext) -> None:
    text = build("live_check", replace(ctx, phone=READY))
    assert "The Pixel is attached now: skip the emulator." in text
    assert "phone_deploy.sh /apps/demo --release --stage install" in text
    assert "Verify only C3, C7" in text
    assert "the toggle survives a restart" in text
    assert "/run/ab12cd34/live_check.emulator.md" in text
    assert "phone_ready.json" not in text


def test_attached_live_check_survives_a_bare_phone_note(ctx: PromptContext) -> None:
    text = build("live_check", replace(ctx, phone={"note": "plug in"}))
    assert "Deploy: the staged build." in text
    assert "Verify only the staged criteria on it (see the plan)" in text

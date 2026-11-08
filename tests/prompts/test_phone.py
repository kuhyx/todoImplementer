"""The phone-last prompt lines: emulator first, staged phone_ready.json, then the attached verification."""

from __future__ import annotations

from dataclasses import replace

from todoimpl.prompts import PromptContext, build
from todoimpl.prompts.kind import HINTS, Kind

READY = {
    "app_dir": "/apps/demo",
    "deploy_cmd": "phone_deploy.sh /apps/demo --release --slot --stage install",
    "criteria": ["C3", "C7"],
    "checks": "the toggle survives a restart",
}


def test_t1520_live_check_stages_the_phone_after_the_emulator(ctx: PromptContext) -> None:
    text = build("live_check", ctx)
    assert "emulator_run.sh boot|install <apk>" in text
    assert "/run/ab12cd34/phone_ready.json" in text
    assert "`- [~] Cn: needs phone: <why>`" in text
    assert "`A: phone: <one line>`" in text
    assert "adb -s emulator-5554 only" in text
    assert "PHONE_DEPLOY_ABI=android-arm64,android-x64" in text
    assert "never install" in text
    assert "shared by parallel runs: never stop it" in text
    assert "Never sign in or add a Firebase account" in text
    assert "shot <png> <pkg>" in text


def test_implement_still_builds_the_release_apk(ctx: PromptContext) -> None:
    assert "release APK" in build("implement", ctx)


def test_t1521_attached_live_check_deploys_and_verifies_only_the_staged_criteria(ctx: PromptContext) -> None:
    text = build("live_check", replace(ctx, phone=READY))
    assert "The Pixel is attached now: skip the emulator." in text
    assert "phone_deploy.sh /apps/demo --release --slot --stage prep|dart|kotlin|assemble|install" in text
    assert "Verify only C3, C7" in text
    assert "the toggle survives a restart" in text
    assert "/run/ab12cd34/live_check.emulator.md" in text
    assert "phone_ready.json" not in text


def test_attached_live_check_survives_a_bare_phone_note(ctx: PromptContext) -> None:
    text = build("live_check", replace(ctx, phone={"note": "plug in"}))
    assert "phone_deploy.sh <app_dir> --release --slot --stage" in text
    assert "Verify only the staged criteria (see the plan)" in text


def test_t1821_attached_check_runs_on_its_own_slot_never_over_the_prod_app(ctx: PromptContext) -> None:
    text = build("live_check", replace(ctx, phone=READY))
    assert "~/.claude/scripts/phone_slot.sh acquire" in text
    assert "com.kuhy.slotN" in text
    assert "--release --slot --stage prep|dart|kotlin|assemble|install" in text
    assert "~/.claude/scripts/phone_vd.sh start <slot pkg>" in text
    assert "tap/swipe/text/shot" in text
    assert "phone_slot.sh release" in text
    assert "in parallel with other runs" in text
    assert "never over kuhy's installed app" in text
    assert "never on the real screen" in text
    assert "sandbox/slot" in text
    assert "SYNC_NAMESPACE" in text
    assert "crdt_sync define" in text


def test_t1822_a_session_never_asks_kuhy_for_hands_on_phone_work(ctx: PromptContext) -> None:
    for phone in (None, READY):
        text = build("live_check", replace(ctx, phone=phone))
        assert "Never ask kuhy to tap, open screens, look at the real screen, plug anything" in text
        assert "pause his music or confirm data use" in text
        assert "slot data is sandboxed" in text


def test_t1823_human_sense_criteria_are_skipped_not_blocking(ctx: PromptContext) -> None:
    for phone in (None, READY):
        text = build("live_check", replace(ctx, phone=phone))
        assert "`- [~] Cn: skipped: needs a human sense`" in text
        assert "unless the note says kuhy wants to check it himself" in text
        assert "`- [~] Cn: after ship: kuhy checks <what>`" in text
        assert "never a blocker" in text


def test_t1824_staged_deploy_command_builds_the_slot_variant(ctx: PromptContext) -> None:
    text = build("live_check", ctx)
    assert "phone_deploy.sh <app_dir> --release --slot --stage prep|dart|kotlin|assemble|install" in text


RULE = "Never install, force-stop, kill, clear, uninstall or launch any non-slot package"


def test_t1834_phone_prompts_protect_kuhys_running_workout_app(ctx: PromptContext) -> None:
    for text in (build("live_check", ctx), build("live_check", replace(ctx, phone=READY))):
        assert RULE in text
        assert "kuhy's running workout app" in text
        assert "phone_deploy exit 46 means stop and report, never work around" in text


def test_t1834_flutter_driver_hint_carries_the_rule() -> None:
    assert "any non-slot package" in HINTS[Kind.FLUTTER]
    assert "exit 46" in HINTS[Kind.FLUTTER]

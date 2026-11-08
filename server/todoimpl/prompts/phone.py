"""Phone-last prompt lines: emulator first, stage the Pixel check, run it once attached."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import PromptContext

IMPLEMENT = (
    "If a criterion needs the Pixel, still build its release APK: live_check tests it on the emulator."
)
BUILD = (
    "ADB_SERIAL=emulator-5554 PHONE_DEPLOY_ABI=android-arm64,android-x64 ~/.claude/scripts/phone_deploy.sh "
    "<app_dir> --release --stage prep|dart|kotlin|assemble (one call each, never install)"
)
EMULATOR = "~/.claude/scripts/emulator_run.sh boot|install <apk>|launch <pkg>|shot <png> <pkg>|release <pkg>"
DEPLOY = (
    "PHONE_DEPLOY_ABI=android-arm64,android-x64 ~/.claude/scripts/phone_deploy.sh {app_dir} --release "
    "--slot --stage prep|dart|kotlin|assemble|install (one call each)"
)
NO_HANDS = (
    "Never ask kuhy to tap, open screens, look at the real screen, plug anything, pause his music or confirm "
    "data use: drive the virtual display yourself (slot data is sandboxed, so real-data concerns do not "
    "apply)."
)
SENSES = (
    "A criterion that needs a human sense (feel a vibration, listen): `- [~] Cn: skipped: needs a human "
    "sense`, never a blocker, unless the note says kuhy wants to check it himself: then "
    "`- [~] Cn: after ship: kuhy checks <what>`, still no blocker."
)
STAGE = (
    '{run_dir}/phone_ready.json = {{"apk": abs path, "pkg", "app_dir": abs path, "versionCode", '
    '"deploy_cmd": "{deploy}", "criteria": ["C7"], "checks": what to verify on the phone}}'
)


def staging(ctx: PromptContext) -> str:
    """Rules for criteria that need the Pixel: emulator first, phone install staged, rows marked `[~]`."""
    return (
        "Criteria that need the Pixel: never wait for it. "
        f"(a) Build one APK for both: `{BUILD}`; test the flow on the emulator with `{EMULATOR}`, "
        "adb -s emulator-5554 only. The emulator is shared by parallel runs: never stop it, `release` when "
        "done, on exit 55 retry in 30 s. Never sign in or add a Firebase account there (prod sync data "
        "would be overwritten): sign-in and sync criteria are phone criteria. "
        f"(b) Write {STAGE.format(run_dir=ctx.run_dir, deploy=DEPLOY.format(app_dir='<app_dir>'))}. "
        "(c) Mark those rows `- [~] Cn: needs phone: <why>` and end with `A: phone: <one line>`. "
        f"{NO_HANDS} {SENSES}"
    )


def attached(ctx: PromptContext) -> str:
    """Tell Claude to verify the staged criteria on its own phone slot, never on kuhy's app or screen."""
    info = ctx.phone or {}
    criteria = ", ".join(str(c) for c in info.get("criteria") or []) or "the staged criteria"
    deploy = DEPLOY.format(app_dir=info.get("app_dir") or "<app_dir>")
    return (
        "The Pixel is attached now: skip the emulator. Test on your own slot, in parallel with other runs, "
        "never over kuhy's installed app and never on the real screen: "
        "`~/.claude/scripts/phone_slot.sh acquire` leases a private id com.kuhy.slotN (never waits); "
        f"build and install it invisibly, one call per stage: `{deploy}` (syncs to sandbox/slotN); "
        "then `~/.claude/scripts/phone_vd.sh start <slot pkg>` and tap/swipe/text/shot on its virtual "
        "display; `phone_slot.sh release` at the end. If the app ignores `SYNC_NAMESPACE` "
        "(--dart-define), add that support (crdt_sync define) first: the one code change this stage allows. "
        f"Verify only {criteria} ({info.get('checks') or 'see the plan'}); never uninstall or `pm clear`. "
        f"Copy the `- [x]` rows of {ctx.run_dir}/live_check.emulator.md unchanged; the rest are yours. "
        f"{NO_HANDS} {SENSES} "
        "If the phone is gone, end with `A: phone: <why>`; anything else you need from kuhy is a plain "
        "`A:` or `Q:`, never `A: phone:`."
    )

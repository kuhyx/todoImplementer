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
    "PHONE_DEPLOY_ABI=android-arm64,android-x64 ~/.claude/scripts/phone_deploy.sh <app_dir> --release "
    "--stage prep|dart|kotlin|assemble|install (one call each)"
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
        f"(b) Write {STAGE.format(run_dir=ctx.run_dir, deploy=DEPLOY)}. "
        "(c) Mark those rows `- [~] Cn: needs phone: <why>` and end with `A: phone: <one line>`."
    )


def attached(ctx: PromptContext) -> str:
    """Tell Claude to deploy the staged build and verify only the staged criteria."""
    info = ctx.phone or {}
    criteria = ", ".join(str(c) for c in info.get("criteria") or []) or "the staged criteria"
    return (
        "The Pixel is attached now: skip the emulator. "
        f"Deploy, one call per stage: {info.get('deploy_cmd') or 'the staged build'}. "
        f"Verify only {criteria} on it ({info.get('checks') or 'see the plan'}) "
        "with ~/.claude/scripts/phone_vd.sh; "
        "never uninstall or `pm clear`. "
        f"Copy the `- [x]` rows of {ctx.run_dir}/live_check.emulator.md unchanged; the rest are yours. "
        "If the phone is gone, end with `A: phone: <why>`."
    )

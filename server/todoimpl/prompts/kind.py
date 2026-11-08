"""Guess what kind of project a worktree is, so live_check names the right driver."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path


class Kind(StrEnum):
    """Project kinds that need a different way to drive the live thing."""

    WEB = "web"  # astro / vite / plain web: package.json
    FLUTTER = "flutter"
    GODOT = "godot"
    PYTHON = "python"  # cli or server
    SHELL = "shell"
    UNKNOWN = "unknown"


# Checked in order: a Flutter or Godot repo often carries a package.json for tooling, so it must not win.
_MARKERS: tuple[tuple[str, Kind], ...] = (
    ("pubspec.yaml", Kind.FLUTTER),
    ("project.godot", Kind.GODOT),
    ("package.json", Kind.WEB),
    ("pyproject.toml", Kind.PYTHON),
    ("setup.py", Kind.PYTHON),
)

# Driver hints from the e2e-ground-truth skill, section 4. Never kuhy's live display :0.
HINTS: dict[Kind, str] = {
    Kind.WEB: (
        "Serve it with `systemd-run --user --collect --unit <name> <dev cmd>`. Drive it with headless "
        "`/usr/bin/chromium --headless=new --disable-extensions --mute-audio`, own `--user-data-dir`, "
        "`--remote-debugging-port=9333`, explicit `--window-size`; click, type, read the DOM and "
        "screenshot over CDP."
    ),
    Kind.FLUTTER: (
        "Flutter web: flutter-web-drive MCP (`start`, `tree`, `tap`/`text`/`key`, `wait`, `shot`). "
        "Phone companion app (com.kuhy.*), Pixel attached: on your own slot only, never kuhy's app: "
        "`~/.claude/scripts/phone_slot.sh acquire`, `phone_deploy.sh <app> --release --slot --stage "
        "prep|dart|kotlin|assemble|install`, `~/.claude/scripts/phone_vd.sh start <slot pkg>` then "
        "tap/swipe/text/shot, `phone_slot.sh release`. Never uninstall or `pm clear`."
    ),
    Kind.GODOT: (
        "godot-mcp-runtime: `run_project`, `simulate_input`, `take_screenshot`. Or the repo's "
        "`scripts/autodrive*.sh` under `capped.sh timeout 55 xvfb-run -a` with `--audio-driver Dummy`."
    ),
    Kind.PYTHON: (
        "Run the real CLI, or start the server with `systemd-run --user --collect --unit <name> <cmd>` "
        "(never `setsid`, never under capped.sh) and `curl` its real port. Re-check the unit after 60 s."
    ),
    Kind.SHELL: (
        "Run the script itself against a scratch dir; show its real stdout and exit code. Services: "
        "`systemd-run --user --collect` then `curl` or read the unit's journal."
    ),
    Kind.UNKNOWN: (
        "No known driver: find the real entrypoint, run it, and observe its output or window "
        "the way a user would."
    ),
}


def detect_kind(worktree: Path) -> Kind:
    """Return the project kind from marker files at the worktree root (not nested ones)."""
    for name, kind in _MARKERS:
        if (worktree / name).is_file():
            return kind
    if any(worktree.glob("*.sh")):
        return Kind.SHELL
    return Kind.UNKNOWN

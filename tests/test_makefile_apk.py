"""A session's release APK builds only the ABIs a check can run (T2483).

A cold `flutter build apk --release` compiled Dart AOT for arm, arm64 and x64 and held a build slot 62 s under
load. The Pixel is arm64 and the emulator x64, so `make apk` drops 32-bit arm; CI still builds the fat APK.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def recipe(target: str) -> str:
    """Return the recipe lines of one Makefile target."""
    return (ROOT / "Makefile").read_text().split(f"\n{target}:\n", 1)[1].split("\n\n", 1)[0]


def test_t2483_make_apk_builds_arm64_and_x64_only() -> None:
    line = recipe("apk")
    assert "flutter build apk --release" in line
    assert "--target-platform android-arm64,android-x64" in line


def test_t2483_claude_md_names_make_apk_and_ci_keeps_every_abi() -> None:
    assert "- apk: `make apk`" in (ROOT / "CLAUDE.md").read_text()
    assert "--target-platform" not in (ROOT / ".github" / "workflows" / "app.yml").read_text()

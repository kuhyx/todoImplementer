"""A session's release APK builds only the ABIs a check can run (T2483/T2506).

A cold `flutter build apk --release` compiled Dart AOT for arm, arm64 and x64 and held a build slot 62 s under
load. The Pixel is arm64 and the emulator x64, so `make apk` drops 32-bit arm; CI still builds the fat APK.
T2506: without disabling lint the `lintVitalAnalyzeRelease` + `lintVitalReportRelease` phases pushed cold from
~13 s toward 67 s and blocked a build slot. Lint disabled: warm ~13 s, cold ~24 s (was 67 s).
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


def test_t2506_gradle_lint_disabled_for_live_check() -> None:
    build_gradle = (ROOT / "app" / "android" / "app" / "build.gradle.kts").read_text()
    assert "lint {" in build_gradle
    assert "checkReleaseBuilds = false" in build_gradle


def test_t2506_gradle_configuration_cache_disabled() -> None:
    gradle_properties = (ROOT / "app" / "android" / "gradle.properties").read_text()
    # Flutter Gradle plugin calls Task.project at execution time; unsupported with config cache
    assert "org.gradle.configuration-cache=true" not in gradle_properties

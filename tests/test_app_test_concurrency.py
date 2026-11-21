"""The app's flutter test fits the 2 GiB capped.sh scope and a 60 s build slot (T2428)."""

from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "app" / "dart_test.yaml"


def test_t2428_app_tests_run_three_isolates_at_most() -> None:
    lines = [line for line in CONFIG.read_text().splitlines() if line.startswith("concurrency:")]
    assert lines == ["concurrency: 3"]

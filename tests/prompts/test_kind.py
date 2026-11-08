"""Kind detection from marker files."""

from __future__ import annotations

from pathlib import Path

import pytest
from todoimpl.prompts import Kind, detect_kind
from todoimpl.prompts.kind import HINTS


@pytest.mark.parametrize(
    ("files", "kind"),
    [
        (["package.json"], Kind.WEB),
        (["pubspec.yaml"], Kind.FLUTTER),
        (["pubspec.yaml", "package.json"], Kind.FLUTTER),
        (["project.godot", "package.json"], Kind.GODOT),
        (["pyproject.toml"], Kind.PYTHON),
        (["setup.py"], Kind.PYTHON),
        (["package.json", "pyproject.toml"], Kind.WEB),
        (["run.sh", "README.md"], Kind.SHELL),
        (["pyproject.toml", "run.sh"], Kind.PYTHON),
        (["README.md"], Kind.UNKNOWN),
        ([], Kind.UNKNOWN),
    ],
)
def test_detect_kind(tmp_path: Path, files: list[str], kind: Kind) -> None:
    for name in files:
        (tmp_path / name).write_text("x")
    assert detect_kind(tmp_path) is kind


def test_missing_dir_is_unknown(tmp_path: Path) -> None:
    assert detect_kind(tmp_path / "nope") is Kind.UNKNOWN


def test_marker_must_be_a_file(tmp_path: Path) -> None:
    (tmp_path / "package.json").mkdir()
    assert detect_kind(tmp_path) is Kind.UNKNOWN


def test_every_kind_has_a_hint() -> None:
    assert set(HINTS) == set(Kind)


def test_t1825_flutter_hint_drives_the_phone_on_its_own_slot() -> None:
    hint = HINTS[Kind.FLUTTER]
    assert "phone_slot.sh acquire" in hint
    assert "--release --slot --stage" in hint
    assert "phone_vd.sh start <slot pkg>" in hint
    assert "phone_slot.sh release" in hint
    assert "--shot" not in hint

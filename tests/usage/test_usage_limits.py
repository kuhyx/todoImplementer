from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from todoimpl.usage import LimitState, limit_state

if TYPE_CHECKING:
    from pathlib import Path


def test_no_files_means_no_limit(tmp_path: Path) -> None:
    assert limit_state(tmp_path) == LimitState(until=None)


def test_until_is_read(tmp_path: Path) -> None:
    (tmp_path / "limit-until").write_text("1788000000\n")
    st = limit_state(tmp_path)
    assert st == LimitState(until=1788000000.0)
    assert st.active(1787999999.0)
    assert not st.active(1788000000.0)


@pytest.mark.parametrize("text", ["", "soon", "nan", "inf"])
def test_garbage_until_is_no_limit(tmp_path: Path, text: str) -> None:
    (tmp_path / "limit-until").write_text(text)
    st = limit_state(tmp_path)
    assert st.until is None
    assert not st.active(0.0)

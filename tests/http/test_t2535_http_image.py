"""T2535: GET /api/image/<folder>/<file> serves a note image from the todo-images folder, nothing else."""

from __future__ import annotations

from typing import TYPE_CHECKING

from httpfakes import Live, call

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 16


def test_t2535_image_route_serves_bytes_and_refuses_bad_paths(
    live: Live, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TODOIMPL_IMAGES_ROOT", str(tmp_path))
    (tmp_path / "abc").mkdir()
    (tmp_path / "abc" / "1.png").write_bytes(PNG)
    ok = call(live.port, "GET", "/api/image/abc/1.png")
    assert (ok.status, ok.body, ok.headers["content-type"]) == (200, PNG, "image/png")
    assert "max-age=86400" in ok.headers["cache-control"]
    for path, status in (
        ("/api/image/../x", 400),
        ("/api/image/abc/..%2Fx.png", 400),
        ("/api/image/abc/2.png", 404),
    ):
        assert call(live.port, "GET", path).status == status, path

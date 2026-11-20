"""Every build is named after a city near Warsaw, one name per commit (part 89abc8ca-2)."""

import subprocess
import threading
from pathlib import Path

import pytest
from httpfakes import FakeBackend, call
from todoimpl.http import buildname
from todoimpl.http import main as http_main
from todoimpl.http.app import make_server


def test_names_start_nearest_warsaw_and_never_repeat() -> None:
    size = len(buildname.CITIES)
    names = [buildname.name(n) for n in range(1, 3 * size + 1)]
    assert names[0] == "Radom"
    assert names[size] == "Radom 2"
    assert len(set(names)) == len(names)
    assert all(len(city) >= 4 and " " not in city for city in buildname.CITIES)


def test_the_name_comes_from_the_commit_count(tmp_path: Path) -> None:
    git = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for n in range(2):
        subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", f"c{n}"], check=True)
    assert http_main.git_build_name(tmp_path) == buildname.name(2)
    assert http_main.git_build_name(tmp_path / "none") == "unknown"


def test_pages_carry_the_name(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<head></head>", encoding="utf-8")
    server = make_server(FakeBackend(), "127.0.0.1", 0, dist=tmp_path, build="b1", build_name="Radom")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        html = call(server.server_address[1], "GET", "/").body.decode()
    finally:
        server.shutdown()
        server.server_close()
    assert 'name="todoimpl-build-name" content="Radom"' in html
    assert 'name="todoimpl-build" content="b1"' in html


def test_serve_names_the_build_from_git(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def fake_make(*_args: object, **kwargs: object) -> object:
        seen.update(kwargs)
        raise SystemExit

    monkeypatch.setattr("todoimpl.http.main.make_server", fake_make)
    monkeypatch.setattr("todoimpl.http.main.git_build_name", lambda _repo: "Lublin")
    with pytest.raises(SystemExit):
        http_main.serve(FakeBackend(), port=0, dist=tmp_path, build="b1")
    assert seen["build_name"] == "Lublin"


def test_no_git_means_unknown(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def no_git(*_args: object, **_kwargs: object) -> None:
        raise OSError

    monkeypatch.setattr("todoimpl.http.main.subprocess.run", no_git)
    assert http_main.git_build_name(tmp_path) == "unknown"

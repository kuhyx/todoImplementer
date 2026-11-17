"""serve() guards and the command line."""

import subprocess
import sys
import threading
import types
from pathlib import Path
from typing import Any

import pytest
from httpfakes import FakeBackend, call
from todoimpl.http import main as http_main
from todoimpl.http.app import make_server


def test_serve_refuses_a_non_loopback_host() -> None:
    with pytest.raises(ValueError, match="loopback"):
        http_main.serve(FakeBackend(), host="0.0.0.0", port=0)  # noqa: S104 - the point of the test


def test_serve_runs_until_stopped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "index.html").write_text("<head></head>", encoding="utf-8")
    ready = threading.Event()
    box: dict[str, Any] = {}
    real_make = make_server

    def capture(*args: Any, **kwargs: Any) -> Any:
        box["server"] = real_make(*args, **kwargs)
        ready.set()
        return box["server"]

    monkeypatch.setattr("todoimpl.http.main.make_server", capture)
    thread = threading.Thread(
        target=http_main.serve, args=(FakeBackend(),), kwargs={"port": 0, "dist": tmp_path, "build": "b1"}
    )
    thread.start()
    assert ready.wait(5)
    port = box["server"].server_address[1]
    assert call(port, "GET", "/version").json()["build"] == "b1"
    box["server"].shutdown()
    thread.join(5)
    assert not thread.is_alive()


def test_git_build_id_outside_a_repo_is_unknown(tmp_path: Path) -> None:
    assert http_main.git_build_id(tmp_path) == "unknown"


def test_git_build_id_in_a_repo_is_the_short_hash(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "x",
        ],
        check=True,
    )
    head = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    assert head.stdout.startswith(http_main.git_build_id(tmp_path))
    assert 4 <= len(http_main.git_build_id(tmp_path)) < 40


def test_git_build_id_without_git_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    assert http_main.git_build_id(tmp_path) == "unknown"


def test_main_wires_the_loaded_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    backend = FakeBackend()
    monkeypatch.setattr(http_main, "load_backend", lambda: backend)
    monkeypatch.setattr(http_main, "serve", lambda b, host, port: seen.update(b=b, host=host, port=port))
    assert http_main.main(["--port", "0"]) == 0
    assert seen == {"b": backend, "host": "127.0.0.1", "port": 0}


def test_main_reports_a_backend_that_cannot_load(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom() -> Any:
        raise ImportError("no scheduler")

    monkeypatch.setattr(http_main, "load_backend", boom)
    assert http_main.main([]) == 2
    assert "no scheduler" in capsys.readouterr().err


def test_main_ctrl_c_exits_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt(*_: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(http_main, "load_backend", FakeBackend)
    monkeypatch.setattr(http_main, "serve", interrupt)
    assert http_main.main([]) == 0


def test_serve_without_on_ready_closes_the_server(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    class Stub:
        router = None  # serve() hands it to the relay, which stays off in tests

        def serve_forever(self) -> None:
            events.append("served")

        def server_close(self) -> None:
            events.append("closed")

    monkeypatch.setattr("todoimpl.http.main.make_server", lambda *_a, **_k: Stub())
    http_main.serve(FakeBackend(), build="x")
    assert events == ["served", "closed"]


def test_serve_defaults_the_build_to_git(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class Stub:
        router = None  # serve() hands it to the relay, which stays off in tests

        def serve_forever(self) -> None:
            return None

        def server_close(self) -> None:
            return None

    def fake_make(*args: Any, **kwargs: Any) -> Stub:
        seen.update(kwargs)
        return Stub()

    monkeypatch.setattr("todoimpl.http.main.make_server", fake_make)
    monkeypatch.setattr(http_main, "git_build_id", lambda _repo: "g1t")
    http_main.serve(FakeBackend())
    assert seen["build"] == "g1t"


def test_load_backend_uses_todoimpl_service(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = FakeBackend()
    module = types.ModuleType("todoimpl.service")
    module.build_backend = lambda: backend  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "todoimpl.service", module)
    assert http_main.load_backend() is backend

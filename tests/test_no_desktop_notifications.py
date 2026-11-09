"""kuhy's decision: no desktop notifications; every alert shows only inside todoImplementer."""

from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "server"


def test_no_server_module_invokes_notify_send() -> None:
    offenders = [
        path.relative_to(SERVER).as_posix()
        for path in SERVER.rglob("*.py")
        if "notify-send" in path.read_text(encoding="utf-8")
        or "notify_send" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []

"""Phone-flow test helpers: a fake adb on PATH, staged phone_ready.json, canned `A: phone:` turns."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from runnerfakes import Env, executable
from schedfakes import CARD, reply

SHIMS = Path(__file__).resolve().parents[1] / "shims"
SERIAL = "23181JEGR08034"
READY = {
    "apk": "/apps/demo/app-release.apk",
    "pkg": "com.kuhy.demo",
    "app_dir": "/apps/demo",
    "versionCode": 7,
    "deploy_cmd": "phone_deploy.sh /apps/demo --release --stage install",
    "criteria": ["C1"],
    "checks": "open the app and see hi",
}


def fake_adb(world: Env, *devices: str) -> Path:
    """Put an `adb` shim in the world's bin; `devices` are its `<serial> <state>` lines. Returns its dir."""
    base = world.tmp / "adb"
    base.mkdir(exist_ok=True)
    (base / "devices").write_text("".join(f"{d}\n" for d in devices), encoding="utf-8")
    shim = f'#!/bin/sh\nFAKE_ADB_DIR="{base}" exec "{sys.executable}" "{SHIMS / "adb"}" "$@"\n'
    executable(world.bin / "adb", shim)
    return base


def adb_calls(base: Path) -> list[str]:
    """Every fake-adb invocation so far."""
    path = base / "calls"
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def phone_turn(world: Env, *, tag: str = "A: phone: plug in the Pixel") -> tuple[dict[str, Any], ...]:
    """Return a turn that stages phone_ready.json in the run dir and ends on `tag`."""
    ready = world.root / CARD / "phone_ready.json"
    return (
        {"_fake": "write", "path": str(ready), "text": json.dumps(READY)},
        *reply(f"C1: done on the emulator\n\n{tag}"),
    )

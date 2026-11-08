"""Helpers for the adopt tests: fabricated turn files, a TurnEnv, a crash that no `except Exception` sees."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from todoimpl.runner import files, orphans
from todoimpl.runner.turn import TurnEnv

if TYPE_CHECKING:
    from pathlib import Path

    from runnerfakes import Env

STEM = "implement-1.000"


class Crash(BaseException):
    pass


def line(obj: dict[str, Any]) -> bytes:
    return (json.dumps(obj) + "\n").encode()


def text(text: str) -> bytes:
    return line({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})


def result(text: str, cost: float = 0.01) -> bytes:
    return line(
        {"type": "result", "result": text, "session_id": "s1", "total_cost_usd": cost, "num_turns": 1}
    )


def finished_turn(run_dir: Path, stem: str, role: str, *lines: bytes, code: int = 0) -> orphans.Record:
    """Fabricate what a host leaves behind: record, stream and exit record."""
    run_dir.mkdir(parents=True, exist_ok=True)
    rec = orphans.begin(run_dir, stem, role, None)
    (run_dir / f"{stem}.stream.jsonl").write_bytes(b"".join(lines))
    files.write_json(run_dir / f"{stem}.exit.json", {"code": code, "ended": 1.0, "pid": 1})
    return rec


def env(run_dir: Path, wt: Path, events: list[dict[str, Any]], handles: list[Any] | None = None) -> TurnEnv:
    return TurnEnv(run_dir, wt, events.append, (handles if handles is not None else []).append, lambda: 100.0)


def kinds(events: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(e["kind"], e["text"]) for e in events if e["type"] == "activity"]


def rig(world: Env, tmp_path: Path) -> tuple[Path, Path]:
    run_dir = tmp_path / "abcd1234-0"
    wt = tmp_path / "abcd1234-demo"
    wt.mkdir()
    run_dir.mkdir()
    return run_dir, wt


def go(_situation: str) -> str:
    return "go"

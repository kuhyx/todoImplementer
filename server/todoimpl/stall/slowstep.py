"""A repo's own gate/test step that ran over 60 s becomes a ticket in that repo (T2437).

A stall whose job is a repo's OWN gate or test step is filed against the card's repo,
the same way heavy builds are. Every other stall stays a todoImplementer perf.stall ticket.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from todoimpl import atomic
from todoimpl.errors.sources import state_base
from todoimpl.runner import heavybuild
from todoimpl.runner.files import read_json

FILE = "slow-steps.json"
KIND = "perf.slowstep"
PREFIX = "slow-"
MESSAGE = "a gate step ran over 60 s with no activity ({what}); make it finish under 60 s"

# Env assignment prefix: VAR=value
ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# Gate step forms:
# scripts/check_gate_stamp.sh step <id>
# .../gate_stamp.sh step <id>
GATE_STEP = re.compile(r"(?:.*/)?(?:check_)?gate_stamp\.sh\s+step\s+(\S+)")

# Test shard forms:
# scripts/test_shard.sh <shard>
TEST_SHARD = re.compile(r"(?:.*/)?test_shard\.sh\s+(\S+)")
# scripts/test.sh --shard N/M (T2450)
SHARD_FLAG = re.compile(r"(?:^|[\s/])test\.sh\s+--shard[=\s](\d+)/(\d+)")


def step_of(command: str) -> str | None:
    """Return the step name when the job is a repo-owned gate/test step, else None.

    Matches (command may have 2>&1 | head -2 etc. after it, and env assignments before):
    - scripts/check_gate_stamp.sh step <id> -> <id> (e.g. gate-test-s3)
    - scripts/test_shard.sh <shard> -> test-shard-<shard>
    - scripts/test.sh --shard N/M -> test-shard-N-M
    - anything else -> None
    """
    # Strip env assignments from the front
    words = [w for w in command.split() if not ASSIGN.match(w)]
    if not words:
        return None
    cmd = " ".join(words)

    m = GATE_STEP.search(cmd)
    if m:
        return m.group(1)
    m = TEST_SHARD.search(cmd)
    if m:
        return f"test-shard-{m.group(1)}"
    m = SHARD_FLAG.search(cmd)
    if m:
        return f"test-shard-{m.group(1)}-{m.group(2)}"
    return None


def _iso(at: float) -> str:
    return datetime.fromtimestamp(at, UTC).isoformat(timespec="seconds")


def file(repo: str, step: str, detail: str, now: float) -> None:
    """Write/update the record in state_base() / "app-errors" / FILE.

    Copies heavybuild.file exactly: app = repo name lower-cased and sanitised
    with NOT_APP regex, signature = f"slow-{step}", kind, count, build: 0,
    message, first_seen, then count+1, last_seen, detail, open: True; atomic write.
    """
    path = state_base() / "app-errors" / FILE
    data = read_json(path)
    errors: list[dict[str, Any]] = data.get("errors", []) if isinstance(data, dict) else []
    app = heavybuild.NOT_APP.sub("-", repo.rsplit("/", 1)[-1].lower()).strip("-") or "repo"
    sig = f"{PREFIX}{step}"
    record = next((e for e in errors if e.get("app") == app and e.get("signature") == sig), None)
    if record is None:
        record = {
            "app": app,
            "repo": repo,
            "signature": sig,
            "kind": KIND,
            "count": 0,
            "build": 0,
            "message": MESSAGE.format(what=step),
            "first_seen": _iso(now),
        }
        errors.append(record)
    record.update(
        count=int(record.get("count", 0)) + 1,
        last_seen=_iso(now),
        detail=detail,
        open=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic.write_text(path, json.dumps({"version": 1, "errors": errors}, indent=2) + "\n")

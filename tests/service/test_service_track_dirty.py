"""The manager writes free-issues.jsonl by hand: one odd line must not blank the tracking view."""

from __future__ import annotations

import json

from contract_lib import validate
from servicefakes import Rig
from test_service_track import _umbrella
from todoimpl.umbrella import issues


def test_hand_written_issue_lines_with_odd_types_still_satisfy_the_contract(rig: Rig) -> None:
    card, directory = _umbrella(rig)
    odd = [
        {
            "child": "kuhyx/alpha",
            "phase": "edit",
            "model": "m1",
            "ts": "2026-11-10T14:00:00Z",
            "symptom": "iso ts",
        },
        {"child": "kuhyx/alpha", "phase": 7, "model": ["a"], "ts": True, "symptom": None, "fixed": "yes"},
        {"child": "kuhyx/alpha", "model": None, "ts": 12, "symptom": {"x": 1}},
        {"child": "kuhyx/beta", "phase": "edit", "model": 5, "ts": 3.5, "symptom": "num model"},
    ]
    issues.path(directory).write_text("\n".join(json.dumps(row) for row in odd) + "\n", encoding="utf-8")
    track = rig.backend.umbrella(card)
    assert track is not None
    validate("track", track)
    alpha = track["kids"][0]["last_issue"]
    assert (alpha["phase"], alpha["model"], alpha["ts"]) == ("", None, 12.0)
    assert track["kids"][1]["last_issue"]["model"] is None  # an int is not a model name
    assert track["issues"]["total"] == 4


def test_a_round_row_with_a_key_the_contract_does_not_know_is_trimmed(rig: Rig) -> None:
    row = {"id": "aaaa1111-0", "verdict": "coached", "detail": "", "free": True, "checks": True, "ok": True}
    rounds = [{"n": 1, "width": 1, "next": 2, "children": [{**row, "junk": 1}], "started": 1.0, "ended": 2.0}]
    card, _ = _umbrella(rig, rounds=rounds)
    track = rig.backend.umbrella(card)
    assert track is not None
    validate("track", track)
    assert set(track["rounds"][0]["children"][0]) == {*row, "repo"}

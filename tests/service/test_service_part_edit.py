"""A part's title and text edited from the board land in its note section at once (856c0f0a)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from servicefakes import Rig
from todoimpl.http import partedit
from todoimpl.http.backend import BackendError
from todoimpl.repotask.ids import repo_card_id
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.todo_mcp.model import TodoError, UnreachableError

BODY = "## a\nold a\n\n## b\nold b"


def _seed(rig: Rig) -> tuple[str, str]:
    """Seed a two-part repo note; return the repo card id and the note id."""
    card = rig.note(body=BODY)
    note = next(iter(rig.fake.store.notes))
    return card, note


def _edit(rig: Rig, card: str, part: str, title: str, text: str) -> dict[str, Any]:
    """POST through the route's handler; a service refusal reads as the Router's error body."""
    raw = json.dumps({"part": part, "title": title, "body": text}).encode()
    try:
        answer: dict[str, Any] = json.loads(partedit.handle(rig.backend, card, raw).body)
    except BackendError as exc:
        return {"ok": False, "error": {"code": exc.code, "message": exc.message}}
    return answer


def test_the_edit_lands_in_the_section_and_the_card_shows_it_at_once(rig: Rig) -> None:
    card, note = _seed(rig)
    detail = rig.backend.task(card)
    assert detail is not None
    assert [(p["title"], p["body"], p["edit"]["enabled"]) for p in detail["card"]["parts"]] == [
        ("a", "old a", True),
        ("b", "old b", True),
    ]
    answer = _edit(rig, card, f"{note[:8]}-1", "b new", "new b")
    assert answer["ok"] is True
    assert rig.fake.store.notes[note].text == "demo todos\n\n## a\nold a\n\n## b new\nnew b"
    assert [p["title"] for p in rig.card(card)["parts"]] == ["a", "b new"]  # no wait for the 2 s refresh


def test_a_part_the_running_card_reached_is_refused_before_any_write(rig: Rig) -> None:
    card, note = _seed(rig)
    rig.run(card, "failed")  # Needs you: the run reached part a and waits on kuhy
    answer = _edit(rig, card, f"{note[:8]}-0", "x", "y")
    assert answer["error"] == {"code": "disabled", "message": "the run is on this part"}
    assert rig.fake.store.notes[note].text == f"demo todos\n\n{BODY}"


def test_the_service_refuses_an_unknown_card_or_part(rig: Rig) -> None:
    card, _ = _seed(rig)
    service = rig.backend.part_service
    assert isinstance(service, partedit.PartApi)
    for target, part in ((repo_card_id("kuhyx/none"), "aaaa1111-0"), (card, "aaaa1111-0")):
        with pytest.raises(BackendError) as err:
            service.edit(target, part, "t", "x")
        assert err.value.code == "not_found"


def test_text_that_would_split_the_note_is_a_bad_request(rig: Rig) -> None:
    card, note = _seed(rig)
    answer = _edit(rig, card, f"{note[:8]}-0", "a", "x\n## b2")
    assert answer["error"]["code"] == "bad_request"


def test_a_section_that_moved_meanwhile_is_a_conflict(rig: Rig) -> None:
    card, note = _seed(rig)
    TodoClient(rig.fake.url, rig.fake.token).update_task(note[:8], body="## b\nold b")
    answer = _edit(rig, card, f"{note[:8]}-1", "b2", "x")
    assert answer["error"]["code"] == "conflict"


def test_an_unreachable_todo_app_reads_as_itself(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    card, note = _seed(rig)

    def down(*_args: object) -> None:
        raise UnreachableError("todo MCP unreachable")

    monkeypatch.setattr(TodoClient, "edit_section", down)
    answer = _edit(rig, card, f"{note[:8]}-0", "a", "x")
    assert answer["error"]["code"] == "upstream_unavailable"


def test_a_failed_reread_after_the_write_still_reports_the_edit(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    card, note = _seed(rig)

    def sick(_repo: str) -> None:
        raise TodoError("refresh failed")

    monkeypatch.setattr(rig.backend.cache, "refresh_repo", sick)
    assert _edit(rig, card, f"{note[:8]}-0", "a2", "x")["ok"] is True
    assert "## a2\nx" in rig.fake.store.notes[note].text

"""POST /api/new-task with no repo: a repo-less note triage routes; nothing is started (T2347)."""

from typing import Any

import pytest
from contract_lib import validate
from httpfakes import Live, call
from todoimpl.http.newtask import NewTask


class FakeLoose:
    def __init__(self, card: str) -> None:
        self.card = card
        self.calls: list[NewTask] = []

    def create(self, task: NewTask) -> tuple[str, str | None]:
        self.calls.append(task)
        return "abcd1234", (self.card if task.repo else None)


@pytest.fixture
def made(live: Live) -> FakeLoose:
    fake = FakeLoose(live.backend.task_id)
    live.backend.new_task_service = fake  # type: ignore[attr-defined]
    return fake


def post(live: Live, body: Any) -> Any:
    return call(live.port, "POST", "/api/new-task", body, live.post_headers())


def test_t2347_a_task_with_no_repo_is_a_loose_note_and_presses_nothing(live: Live, made: FakeLoose) -> None:
    body = {"title": "Make a habit app", "body": "streaks"}
    validate("requests", body, "new_task")
    r = post(live, body)
    assert r.status == 200, r.body
    validate("response", r.json())
    assert r.json() == {"ok": True, "note": "abcd1234", "started": False}
    assert made.calls == [NewTask("", "Make a habit app", "streaks", ())]
    assert live.backend.calls == []

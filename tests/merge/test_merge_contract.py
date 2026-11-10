"""contracts/merge.schema.json: the real service output validates; broken shapes do not."""

import copy
from typing import Any

import pytest
from contract_lib import validate
from jsonschema import ValidationError
from mergefakes import Rig
from test_merge_service import Brain, Clock, make

DISABLED = False
SUGGESTION: dict[str, Any] = {
    "id": "0123456789ab",
    "title": "Text-free",
    "reason": "same change",
    "members": [
        {"id": "aaaaaaaa-0", "title": "A", "repo": "kuhyx/a"},
        {"id": "bbbbbbbb-1", "title": "B", "repo": "kuhyx/b"},
    ],
    "actions": [
        {"id": "merge", "label": "Merge", "enabled": True, "reason": None},
        {"id": "dismiss", "label": "Dismiss", "enabled": True, "reason": None},
    ],
}


def test_the_services_answers_validate(rig: Rig) -> None:
    rig.sections("kuhyx/a", [("Make a text-free", "x"), ("Make b text-free", "y")])
    service = make(rig, Brain(), Clock())
    body = service.suggestions()
    assert len(body["suggestions"]) == 1
    validate("merge", body)
    group = body["suggestions"][0]["id"]
    validate("merge", service.merge(group), "response")


def test_good_examples_validate() -> None:
    validate("merge", {"suggestions": []})
    validate("merge", {"suggestions": [SUGGESTION]})
    validate("merge", {"ok": True, "new_id": None, "suggestions": [SUGGESTION]}, "response")
    validate("merge", {"ok": True, "new_id": "aaaaaaaa-3", "suggestions": []}, "response")
    validate("merge", {"ok": False, "error": {"code": "disabled", "message": "live run"}}, "response")
    validate("merge", {}, "merge")
    validate("merge", {}, "dismiss")


def _without(path: list[str | int]) -> dict[str, Any]:
    out = copy.deepcopy(SUGGESTION)
    node: Any = out
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    return out


def _with(path: list[str | int], value: object) -> dict[str, Any]:
    out = copy.deepcopy(SUGGESTION)
    node: Any = out
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return out


@pytest.mark.parametrize(
    "bad",
    [
        _with(["id"], "SHORT"),
        _with(["members"], SUGGESTION["members"][:1]),
        _with(["members", 0, "id"], "aaaaaaaa"),
        _with(["actions"], SUGGESTION["actions"][:1]),
        _with(["actions", 0, "id"], "ship"),
        _with(["actions", 0, "enabled"], DISABLED),
        _with(["extra"], 1),
        _without(["reason"]),
        _without(["members", 0, "repo"]),
    ],
)
def test_bad_suggestions_are_rejected(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        validate("merge", {"suggestions": [bad]})


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ({"x": 1}, "merge"),
        ({"x": 1}, "dismiss"),
        ({"ok": True, "suggestions": []}, "response"),
        ({"ok": False}, "response"),
    ],
)
def test_bad_bodies_and_responses_are_rejected(body: dict[str, Any], fragment: str) -> None:
    with pytest.raises(ValidationError):
        validate("merge", body, fragment)

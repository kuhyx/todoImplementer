"""The ticket text: title, body, finding it again and editing its Seen and Tier lines."""

from __future__ import annotations

from errfakes import rec
from todoimpl.errors import ticket
from todoimpl.errors.record import AppError, parse
from todoimpl.repotask.legacy import Older
from todoimpl.service.repocards import group_cards
from todoimpl.todo_mcp.items import sections
from todoimpl.todo_mcp.model import Task


def record(**over: object) -> AppError:
    found = parse(rec(**over))
    assert found is not None
    return found


def note(body: str, repo: str = "kuhyx/kartka") -> Task:
    return Task("aaaa1111", "kartka todos", body, repo, "todo", "medium", None)


def test_the_title_names_app_kind_message_and_the_short_signature() -> None:
    title = ticket.title(record(message="line one\nline two " + "x" * 200))
    assert title.startswith("Fix kartka: crash line one line two xxx")
    assert title.endswith("[02b0d43d]")
    assert "\n" not in title
    assert len(title) < 130


def test_the_body_has_the_goal_the_done_line_and_the_signature_line() -> None:
    text = ticket.body(record())
    lines = text.splitlines()
    assert "Do not ask kuhy anything" in lines[0]
    assert any(line.startswith("done:") for line in lines)  # a done: line spares the Spec stage
    assert "Error: crash: SuwayomiException: x is not on the server" in lines
    assert "Top frame: SuwayomiSource._searchForUnseen (package:kartka/s.dart)" in lines
    assert "Detail: route /library" in lines
    assert "Build: 41 (1.4.0-abc1234)" in lines
    assert "Seen: 3x, first 2026-11-01T10:00:00Z, last 2026-11-02T10:00:00Z" in lines
    assert lines[-1] == "Error-Signature: kartka:02b0d43d9f"
    assert not any(line.startswith("## ") for line in lines)


def test_the_body_skips_unknown_parts_and_cannot_break_the_note() -> None:
    bare = ticket.body(
        record(top_frame=None, detail=None, version_name=None, build=0, message="a ``` b\n## c")
    )
    assert "Top frame" not in bare
    assert "Detail" not in bare
    assert "Build" not in bare
    assert "```" not in bare
    assert not any(line.startswith("## ") for line in bare.splitlines())
    assert "Build: 7" in ticket.body(record(build=7, version_name=None))


def test_a_regression_names_the_old_and_new_build() -> None:
    text = ticket.body(record(build=60), regression=55)
    assert "Regression: seen again on build 60; the fix shipped in build 55." in text
    assert "Regression: seen again, after the fix reached the phone." in ticket.body(
        record(build=0), regression=0
    )


def test_find_reads_the_signature_line_of_an_open_part() -> None:
    other = ticket.body(record(signature="zzz"))
    mine = ticket.body(record())
    body = f"## Fix other\n{other}\n\n## Fix mine\n{mine}\n\n## plain\nno signature here"
    cards = group_cards([note(body)], lambda _c: Older())
    found = ticket.find(cards, "kartka:02b0d43d9f")
    assert found is not None
    assert (found.title, found.note) == ("Fix mine", "aaaa1111")
    assert found.card == cards[0].id
    assert ticket.find(cards, "kartka:nope") is None


def test_find_also_reads_a_card_that_is_one_whole_note() -> None:
    plain = Task("bbbb2222", "Fix solo", ticket.body(record()), None, "todo", "medium", None)
    cards = group_cards([plain], lambda _c: Older())
    found = ticket.find(cards, "kartka:02b0d43d9f")
    assert found is not None
    assert (found.note, found.title) == ("bbbb2222", "Fix solo")


def test_refresh_rewrites_only_the_seen_line_of_that_part() -> None:
    mine = ticket.body(record())
    other = ticket.body(record(signature="zzz"))
    body = f"## Fix other\n{other}\n\n## Fix mine\n{mine}"
    newer = record(count=9, last_seen="2026-11-05T00:00:00Z")
    changed = ticket.refresh(body, newer.key, ticket.seen(newer))
    assert changed is not None
    assert changed.count("Seen: 9x, first 2026-11-01T10:00:00Z, last 2026-11-05T00:00:00Z") == 1
    assert changed.count("Seen: 3x") == 1  # the other part keeps its line
    assert len(sections(changed)) == 2
    assert ticket.refresh(changed, newer.key, ticket.seen(newer)) is None  # nothing new: no write
    assert ticket.refresh(body, "kartka:missing", "Seen: 1x") is None


def test_refresh_adds_a_seen_line_a_hand_edit_removed() -> None:
    text = "## Fix\nsome text\nError-Signature: kartka:1\n"
    got = ticket.refresh(text, "kartka:1", "Seen: 2x")
    assert got is not None
    assert "Seen: 2x\nError-Signature: kartka:1" in got


def test_signatures_lists_every_line_of_a_text() -> None:
    assert ticket.signatures(
        "a\n  Error-Signature: x:1  \nError-Signature: y:2\nnot Error-Signature: z:3"
    ) == ["x:1", "y:2"]

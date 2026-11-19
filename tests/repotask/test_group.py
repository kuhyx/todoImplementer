"""Grouping notes into one card per repo (T1888) and the parts it lists."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from todoimpl.repotask.ids import norm, repo_card_id
from todoimpl.repotask.legacy import Older
from todoimpl.service.repocards import group_cards, section_cards
from todoimpl.todo_mcp.model import Task

if TYPE_CHECKING:
    from collections.abc import Callable

NEVER = lambda _card: Older()  # noqa: E731 - no older run owns any section


def holding(*cards: str) -> Callable[[str], Older]:
    return lambda card: Older(held=card in cards)


UMBRELLA = "Umbrella: per-repo\n- [ ] kuhyx/a (aaaa1111)\n## kuhyx/a (aaaa1111)\ntext"


def note(
    id8: str, repo: str | None, body: str = "", title: str = "notes", priority: str = "medium", **fields: str
) -> Task:
    return Task(id8, title, body, repo, fields.get("status", "todo"), priority, fields.get("done_check"))


def test_t1911_all_notes_and_sections_of_a_repo_are_one_card() -> None:
    notes = [
        note("aaaa1111", "kuhyx/tutor", "## text-free leftovers\nx\n\n## server s\ny"),
        note("bbbb2222", "kuhyx/tutor", "Make tutor text-free"),
        note("cccc3333", "kuhyx/tutor", "## one more\nz"),
        note("dddd4444", "kuhyx/other", "## alone\nq"),
    ]
    cards = group_cards(notes, NEVER)
    assert sorted(card.repo or "" for card in cards) == ["kuhyx/other", "kuhyx/tutor"]
    tutor = next(card for card in cards if card.repo == "kuhyx/tutor")
    assert tutor.id == repo_card_id("kuhyx/tutor")
    assert [p.key for p in tutor.parts] == ["aaaa1111-0", "aaaa1111-1", "cccc3333-0", "bbbb2222-0"]
    assert tutor.item.note_id == tutor.id.partition("-")[0]


def test_the_card_id_does_not_change_when_notes_come_and_go() -> None:
    one = group_cards([note("aaaa1111", "kuhyx/tutor", "x")], NEVER)[0]
    two = group_cards([note("zzzz9999", "KuhyX/Tutor ", "y"), note("aaaa1111", "kuhyx/tutor", "x")], NEVER)
    assert [card.id for card in two] == [one.id]
    assert norm(" KuhyX/Tutor ") == "kuhyx/tutor"


def test_parts_run_by_priority_then_easiest() -> None:
    notes = [
        note("aaaa1111", "kuhyx/r", "## big\n" + "long text " * 30, priority="high"),
        note("bbbb2222", "kuhyx/r", "## scan five\nScan x: 5 items", priority="medium"),
        note("cccc3333", "kuhyx/r", "## scan two\nScan x: 2 items", priority="medium"),
        note("dddd4444", "kuhyx/r", "## short\nhi", priority="medium"),
        note("eeee5555", "kuhyx/r", "## low one\nz", priority="low"),
        note("ffff6666", "kuhyx/r", "## odd priority\nz", priority="whatever"),
    ]
    (card,) = group_cards(notes, NEVER)
    assert [p.title for p in card.parts] == [
        "big",
        "scan two",
        "scan five",
        "odd priority",
        "short",
        "low one",
    ]
    assert card.priority == "high"


def test_umbrella_notes_and_notes_without_a_repo_stay_as_they_were() -> None:
    notes = [
        note("uuuu0001", "kuhyx/a", UMBRELLA),
        note("nnnn0002", None, "## x\ny"),
        note("aaaa1111", "kuhyx/a", "## p\nq"),
    ]
    cards = group_cards(notes, NEVER)
    assert sorted(card.id for card in cards) == sorted(["uuuu0001-0", "nnnn0002-0", repo_card_id("kuhyx/a")])
    assert next(card for card in cards if card.id == "uuuu0001-0").parts == ()


def test_done_sections_are_not_parts_and_a_note_without_sections_is_one() -> None:
    (card,) = group_cards([note("aaaa1111", "kuhyx/r", "## [x] shipped\nclosed: ok\n\n## open\nx")], NEVER)
    assert [p.title for p in card.parts] == ["open"]
    (whole,) = group_cards([note("bbbb2222", "kuhyx/r", "plain text", title="Plain note")], NEVER)
    assert [p.title for p in whole.parts] == ["Plain note"]


def test_t1980_manual_parts_sit_on_the_one_repo_card_beside_claude_work() -> None:
    """T1980 as kuhy reversed it on 2026-11-19 (T2114): one card per repo holds both kinds of part."""
    notes = [
        note("aaaa1111", "kuhyx/r", "## real work\nx"),
        note("bbbb2222", "kuhyx/r", "do it", title="MANUAL WORK REQUIRED: rotate the key"),
    ]
    (card,) = group_cards(notes, NEVER)
    assert (card.id, card.title) == (repo_card_id("kuhyx/r"), "r")
    assert sorted((p.title, p.human) for p in card.parts) == [
        ("MANUAL WORK REQUIRED: rotate the key", True),
        ("real work", False),
    ]
    assert "rotate the key" not in card.body  # never in the run's work


def test_a_repo_with_held_and_human_parts_has_one_card_for_kuhy() -> None:
    notes = [
        note("aaaa1111", "kuhyx/r", "## held\nx"),
        note("bbbb2222", "kuhyx/r", "z", title="MANUAL WORK REQUIRED: z"),
    ]
    cards = group_cards(notes, holding("aaaa1111-0"))
    assert sorted(card.id for card in cards) == sorted(["aaaa1111-0", repo_card_id("kuhyx/r")])
    repo = next(card for card in cards if card.parts)
    assert (repo.title, repo.body) == ("MANUAL WORK REQUIRED: z", "")


def test_a_human_part_never_counts_as_held_by_a_stale_run() -> None:
    notes = [note("aaaa1111", "kuhyx/r", "do it", title="MANUAL WORK REQUIRED: rotate")]
    (card,) = group_cards(notes, holding("aaaa1111-0"))
    (part,) = card.parts
    assert (part.human, part.held) == (True, False)


def test_a_repo_with_only_human_parts_reads_as_that_work() -> None:
    (card,) = group_cards([note("bbbb2222", "kuhyx/r", "do it", title="MANUAL WORK REQUIRED: rotate")], NEVER)
    assert (card.id, card.title) == (repo_card_id("kuhyx/r"), "MANUAL WORK REQUIRED: rotate")
    assert card.body == ""


def test_a_part_an_older_run_owns_keeps_its_own_card_and_leaves_the_repo_run() -> None:
    notes = [note("aaaa1111", "kuhyx/r", "## held\nx\n\n## free\ny")]
    cards = group_cards(notes, holding("aaaa1111-0"))
    ids = sorted(card.id for card in cards)
    assert ids == sorted(["aaaa1111-0", repo_card_id("kuhyx/r")])
    repo = next(card for card in cards if card.parts)
    assert [(p.title, p.held) for p in repo.parts] == [("held", True), ("free", False)] or [
        (p.title, p.held) for p in repo.parts
    ] == [("free", False), ("held", True)]
    assert "held" not in repo.body.replace("Part aaaa1111-0", "")
    own = next(card for card in cards if card.id == "aaaa1111-0")
    assert (own.title, own.parts) == ("held", ())


def test_a_part_whose_older_run_ended_is_an_ordinary_part_that_remembers_the_work() -> None:
    def ended(card: str) -> Older:
        return Older(note=f"an earlier run ended failed (branch todo/{card})")

    (card,) = group_cards([note("aaaa1111", "kuhyx/r", "## once\nx")], ended)
    (part,) = card.parts
    assert (part.held, part.actionable) == (False, True)
    assert part.prior == "an earlier run ended failed (branch todo/aaaa1111-0)"
    assert "once" in card.body


def test_a_repo_whose_every_part_is_held_has_no_repo_card() -> None:
    cards = group_cards([note("aaaa1111", "kuhyx/r", "## held\nx")], lambda _card: Older(held=True))
    assert [card.id for card in cards] == ["aaaa1111-0"]


def test_done_checks_are_chained_and_the_status_follows_the_notes() -> None:
    notes = [
        note(
            "aaaa1111",
            "kuhyx/r",
            "## a\ndone_check: make a\n\n## b\ndone_check: make b",
            status="in progress",
        ),
        note("bbbb2222", "kuhyx/r", "## c\ndone_check: make a"),
    ]
    (card,) = group_cards(notes, NEVER)
    assert card.done_check == "( make a ) && ( make b )"
    assert card.status == "in progress"
    (single,) = group_cards([note("cccc3333", "kuhyx/s", "## a\ndone_check: make a\n\n## b\ny")], NEVER)
    assert single.done_check == "make a"
    (none,) = group_cards([note("dddd4444", "kuhyx/t", "## a\ny")], NEVER)
    assert none.done_check is None


def test_section_cards_expand_a_repo_card_back_into_its_open_sections() -> None:
    notes = [note("aaaa1111", "kuhyx/r", "## held\nx\n\n## free\ny"), note("uuuu0001", None, "## u\nz")]
    cards = group_cards(notes, holding("aaaa1111-0"))
    sections = section_cards(cards)
    assert sorted(card.id for card in sections) == ["aaaa1111-0", "aaaa1111-1", "uuuu0001-0"]
    free = next(card for card in sections if card.id == "aaaa1111-1")
    assert (free.item.note_id, free.item.index, free.title, free.body) == ("aaaa1111", 1, "free", "y")


def test_chained_subshell_checks_stay_valid_bash() -> None:
    """A check that is itself a subshell must not merge into bash's `((` arithmetic."""
    body = "## a\ndone_check: ( true )\n\n## b\ndone_check: ( cd / && true )"
    (card,) = group_cards([note("eeee5555", "kuhyx/u", body)], NEVER)
    assert card.done_check is not None
    assert subprocess.run(["bash", "-c", card.done_check], check=False).returncode == 0

"""T2592: a merged umbrella of other apps' tickets showed `medium` on the board (its note's priority).

"Fix perf.slow slow wait across apps" (5 kartka children) is lane `app`, but the Backlog sorts by priority
first, so it stood above kuhy's `low` cards and a Start of one of them asked about the umbrella. A card
whose text is only other apps' reports counts as `low` everywhere (card, picker, outrank), like a repo card.
"""

from __future__ import annotations

from todoimpl.board import outrank, prioaction
from todoimpl.board.status import Status
from todoimpl.errors import ticket
from todoimpl.errors.record import AppError
from todoimpl.repotask import lane
from todoimpl.service.cards import CardTask, card_tasks
from todoimpl.todo_mcp.model import Task


def _ticket(app: str, sig: str) -> str:
    record = AppError(app, f"kuhyx/{app}", sig, "perf.slow", "slow wait", 4, "2026-11-27T13:19:35Z",
                      "2026-11-27T13:19:45Z", 0)  # fmt: skip
    return f"{ticket.title(record)}\n\n{ticket.body(record)}"


def _umbrella(*kids: tuple[str, str]) -> str:
    """Return an umbrella note body as `merge/text.umbrella_text` writes it: (repo, child text) per child."""
    boxes = [f"- [ ] kuhyx/{repo} (abcd000{n})" for n, (repo, _) in enumerate(kids)]
    heads = [f"## kuhyx/{repo} (abcd000{n})\n{text}" for n, (repo, text) in enumerate(kids)]
    return "\n".join(["Umbrella: per-repo", *boxes, *heads])


def _card(body: str, priority: str = "medium", repo: str | None = None) -> CardTask:
    note = Task("3b62f9bc", "Fix perf.slow slow wait across apps", body, repo, "todo", priority, None)
    (card,) = card_tasks(note)
    return card


APP = _umbrella(("kartka", _ticket("kartka", "89e1ec6e3d")), ("kartka", _ticket("kartka", "971debc861")))
BOARD = _umbrella(
    ("kartka", "Fix\nError-Signature: kartka:slow-gate"), ("tutor", "Error-Signature: tutor:slow-x")
)


def test_t2592_an_umbrella_of_app_tickets_is_low() -> None:
    card = _card(APP)
    assert card.priority == "low"
    (picker,) = prioaction.action(card, Status.BACKLOG)
    assert picker.value == "low"
    assert not picker.enabled


def test_t2592_an_old_medium_ticket_note_is_low_too() -> None:
    assert _card(_ticket("kartka", "02b0d43d9f"), repo="kuhyx/kartka").priority == "low"


def test_t2592_kuhys_and_the_boards_cards_keep_their_note_priority() -> None:
    assert _card("Make the kuhy fix.\ndone: it works", "high").priority == "high"
    assert _card(BOARD).priority == "medium"


def test_t2592_starting_kuhys_low_card_names_no_app_umbrella() -> None:
    umbrella = _card(APP)
    (kuhy,) = card_tasks(Task("11112222", "kuhy low", "Do it.", "kuhyx/demo", "todo", "low", None))
    waiting = outrank.backlog([umbrella, kuhy], {})
    assert {c["id"]: c["priority"] for c in waiting} == {umbrella.id: "low", kuhy.id: "low"}
    card = {"id": kuhy.id, "priority": "low", "actions": [{"id": "start", "enabled": True}]}
    outrank.mark(card, waiting)
    assert "waits" not in card["actions"][0]


def test_t2592_a_kuhy_child_among_app_tickets_keeps_the_umbrella_in_kuhys_lane() -> None:
    mixed = _umbrella(
        ("kartka", _ticket("kartka", "89e1ec6e3d")), ("tutor", "Add a dark mode.\ndone: it is dark")
    )
    assert lane.of_text(mixed) == lane.KUHY
    assert _card(mixed).priority == "medium"


def test_t2592_done_children_do_not_count_while_one_is_open() -> None:
    done_kuhy = _umbrella(("tutor", "Add a dark mode."), ("kartka", _ticket("kartka", "89e1ec6e3d")))
    done_kuhy = done_kuhy.replace("## kuhyx/tutor", "## [x] kuhyx/tutor")
    assert lane.of_text(done_kuhy) == lane.APP
    all_done = done_kuhy.replace("## kuhyx/kartka", "## [x] kuhyx/kartka")
    assert lane.of_text(all_done) == lane.KUHY  # every child done: all of them count


def test_t2592_a_same_repo_merge_reads_each_member() -> None:
    merged = f"### 1d66e34e-5\n{_ticket('kartka', '89e1ec6e3d')}\n### 856c0f0a\nEdit a note in the backlog."
    assert lane.of_text(merged) == lane.KUHY
    only_app = (
        f"### 1d66e34e-5\n{_ticket('kartka', '89e1ec6e3d')}\n### 856c0f0a\n{_ticket('kartka', '02b0d43d9f')}"
    )
    assert lane.of_text(only_app) == lane.APP

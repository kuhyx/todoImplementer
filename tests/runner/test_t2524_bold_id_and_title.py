"""T2524: a card written `❓ **Q1 - title**: body` (id and title in one bold) was not parsed as a question."""

from todoimpl.runner import parsing

REPLY = """Intro.

❓ **Q1 - What happens after a note queued during shipping**: A finished ship makes the card Done. Reopen it?
➡️ Reopen it.

❓ **Q2: Second one**: Body two.
➡️ Rec two.

Q:
"""


def test_t2524_bold_id_and_title_parse_as_cards() -> None:
    qs = parsing.parse_questions(REPLY)
    assert [(q.id, q.title, q.body, q.recommendation) for q in qs] == [
        (
            "Q1",
            "What happens after a note queued during shipping",
            "A finished ship makes the card Done. Reopen it?",
            "Reopen it.",
        ),
        ("Q2", "Second one", "Body two.", "Rec two."),
    ]

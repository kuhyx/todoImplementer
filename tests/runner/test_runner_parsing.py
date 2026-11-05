from todoimpl.runner import parsing

GRILL = """Some intro.

❓ **Q1** - **Scope**: Which file should change?
It matters for tests.
➡️ hello.txt only

❓ **Q2** - **Style**: Match which file?
➡ main.py

❓ **Q3** plain title line
➡️ yes
stray line after the recommendation
❓ **Q1** - **Scope again**: replaced
➡️ new rec
"""


def test_parse_questions_reads_cards_with_or_without_fe0f() -> None:
    qs = parsing.parse_questions(GRILL)
    assert [(q.id, q.title, q.body, q.recommendation, q.answer) for q in qs] == [
        ("Q1", "Scope again", "replaced", "new rec", None),
        ("Q2", "Style", "Match which file?", "main.py", None),
        ("Q3", "plain title line", "", "yes", None),
    ]
    assert parsing.parse_questions("no questions\n➡️ orphan") == []


def test_parse_criteria_reads_the_acceptance_section() -> None:
    plan = (
        "# Plan\n- not a criterion\n## Acceptance criteria\n- hello.txt exists\n"
        "1. `cat hello.txt` prints hi\n\n## Steps\n- x"
    )
    assert parsing.parse_criteria(plan) == ["hello.txt exists", "`cat hello.txt` prints hi"]
    assert parsing.parse_criteria("## Steps\n- x") == []


def test_parse_self_check_and_live_rows() -> None:
    text = "- C1: done - ran `ls`, saw hello.txt\n`C2: not done (prints ho)`\n"
    text += "hello.txt exists: done\nStatus fine\nD: done"
    assert parsing.parse_self_check(text) == [
        {"criterion": "C1", "done": True, "note": "ran `ls`, saw hello.txt"},
        {"criterion": "C2", "done": False, "note": "prints ho"},
        {"criterion": "hello.txt exists", "done": True, "note": ""},
    ]
    live = "# Live\n- [x] C1: ran `cat hello.txt` -> saw hi\n"
    live += "- [ ] C2: could not start the app\n* [X] no id here\nx"
    assert parsing.parse_live(live) == [
        {"criterion": "C1", "done": True, "note": "ran `cat hello.txt` -> saw hi"},
        {"criterion": "C2", "done": False, "note": "could not start the app"},
        {"criterion": "no id here", "done": True, "note": "no id here"},
    ]


def test_parse_criteria_reads_c_numbered_bullets() -> None:
    plan = "## Approach\n- touch x\n## Acceptance criteria\nC1. I run `cat hello.txt`, I see hi\nC2: second\n"
    assert parsing.parse_criteria(plan) == ["I run `cat hello.txt`, I see hi", "second"]

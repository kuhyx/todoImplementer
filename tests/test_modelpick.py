"""A note that is a model command names a model id (or `default`); every other note stays a note (T2215)."""

import pytest
from todoimpl import modelpick

FABLE, OPUS, SONNET, HAIKU = (m.id for m in modelpick.MODELS)


@pytest.mark.parametrize(
    ("note", "model"),
    [
        ("run it on claude fable 5.2", FABLE),
        ("Run it on Claude Fable 5.2.", FABLE),
        ("fable", FABLE),
        ("fable 5.2", FABLE),
        ("claude fable 5.2", FABLE),
        ("claude-fable-5-2", FABLE),
        ("rerun on opus", OPUS),
        ("re-run this on opus 5.5 please", OPUS),
        ("use sonnet 5.5", SONNET),
        ("switch to sonnet", SONNET),
        ("on haiku", HAIKU),
        ("try it again with haiku 5", HAIKU),
        ("default", modelpick.DEFAULT),
        ("go back to the default model", modelpick.DEFAULT),
        ("use default", modelpick.DEFAULT),
    ],
)
def test_t2215_a_model_note_names_the_model(note: str, model: str) -> None:
    assert modelpick.parse(note) == model


@pytest.mark.parametrize(
    "note",
    [
        "run it on gpt 5",  # an unknown model: a normal note
        "run it on opus 4.1",  # a version that is not ours
        "use sonnet 5.5 for the classifier",  # more words: an instruction to the session
        "the opus logo looks bad",
        "make the default theme darker",
        "",
        "ok",
    ],
)
def test_t2215_any_other_note_is_no_model_command(note: str) -> None:
    assert modelpick.parse(note) is None


def test_t2215_the_picker_offers_every_model_then_default() -> None:
    rows = modelpick.choices()
    assert [r["id"] for r in rows] == list(modelpick.IDS)
    assert rows[0] == {"id": FABLE, "label": "Fable 5.2"}
    assert modelpick.label(OPUS) == "Opus 5.5"
    assert modelpick.label("opus") == "opus"

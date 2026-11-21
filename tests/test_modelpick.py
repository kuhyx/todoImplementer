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


def test_t2215_the_picker_offers_every_model() -> None:
    rows = modelpick.choices()
    assert [r["id"] for r in rows] == list(
        modelpick.IDS[:-1]
    )  # `default` stays a note word, no button (T2470)
    assert rows[0] == {"id": FABLE, "label": "Fable 5.2"}
    assert modelpick.label(OPUS) == "Opus 5.5"
    assert modelpick.label("opus") == "opus"


@pytest.mark.parametrize(
    ("note", "model", "rest"),
    [
        ("run it on claude fable 5.2\nMake the logo bolder", FABLE, "Make the logo bolder"),
        ("run it on claude fable 5.2. Make the logo bolder.", FABLE, "Make the logo bolder."),
        ("rerun on opus, and keep the old palette", OPUS, "keep the old palette"),
        ("run on sonnet; only the header", SONNET, "only the header"),
        ("switch to haiku: summarise the log", HAIKU, "summarise the log"),
        ("Run it on Fable and try three new logos", FABLE, "try three new logos"),
        ("re-run on claude-fable-5-2 - no gradients", FABLE, "no gradients"),
        ("run it on fable 5.2", FABLE, ""),  # a whole command has no rest
        ("default", modelpick.DEFAULT, ""),
        ("run it on fable.", FABLE, ""),  # a separator with nothing after it: the whole command
    ],
)
def test_t2221_a_note_that_starts_with_a_model_command_pins_it_and_keeps_the_rest(
    note: str, model: str, rest: str
) -> None:
    assert modelpick.command(note) == (model, rest)


@pytest.mark.parametrize(
    "note",
    [
        "use sonnet 5.5 for the classifier",  # `use X for` stays a note
        "use opus, and make it blue",  # only run / rerun / switch lead a note
        "the logo, run it on fable later",  # a model name mid-sentence
        "run it on gpt 5, then ship",  # an unknown model
        "run it on fable 4.0. then ship",  # a version that is not ours
    ],
)
def test_t2221_other_notes_stay_notes(note: str) -> None:
    assert modelpick.command(note) is None

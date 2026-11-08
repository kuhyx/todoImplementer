import json
import stat
from datetime import date
from pathlib import Path

import pytest
from apikeyfakes import KEY, OTHER, USER_KEY
from todoimpl.apikey import store

D1, D2 = date(2026, 11, 1), date(2026, 12, 1)


def test_default_paths_live_under_home(home: Path) -> None:
    assert store.key_path() == home / ".config" / "todoImplementer" / "anthropic_api_key"
    assert store.meta_path() == store.key_path().with_name("anthropic_api_key.json")


def test_env_override_moves_both_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIMPL_APIKEY", str(tmp_path / "k"))
    assert store.key_path() == tmp_path / "k"
    assert store.meta_path() == tmp_path / "k.json"


@pytest.mark.parametrize("text", [KEY, OTHER, "sk-ant-api04-" + "a_-" * 30, USER_KEY, "sk-ant-" + "c" * 20])
def test_is_key_accepts_real_shapes(text: str) -> None:
    assert store.is_key(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hello",
        "sk-ant-api03-short",
        "sk-ant-" + "c" * 19,
        KEY + "\n",
        KEY[:-1] + "!",
        "x" + KEY,
        KEY + " " + KEY,
    ],
)
def test_is_key_rejects_everything_else(text: str) -> None:
    assert not store.is_key(text)


def test_read_key_missing_empty_and_malformed_are_none() -> None:
    assert store.read_key() is None
    assert store.read_raw() is None
    store.key_path().parent.mkdir(parents=True)
    store.key_path().write_text("  \n")
    assert store.read_key() is None
    assert store.read_raw() is None
    store.key_path().write_text("garbage\n")
    assert store.read_key() is None
    assert store.read_raw() == "garbage"


def test_read_key_strips_the_newline() -> None:
    store.key_path().parent.mkdir(parents=True)
    store.key_path().write_text(KEY + "\n")
    assert store.read_key() == KEY


def test_read_raw_unreadable_file_is_none() -> None:
    store.key_path().mkdir(parents=True)  # a directory where the file should be
    assert store.read_raw() is None


def test_save_writes_both_files_0600_and_round_trips() -> None:
    store.save(KEY, D1, D2)
    assert store.read_key() == KEY
    meta = store.read_meta()
    assert meta is not None
    assert (meta.created, meta.expires) == (D1, D2)
    assert json.loads(store.meta_path().read_text()) == {"created": "2026-11-01", "expires": "2026-12-01"}
    for path in (store.key_path(), store.meta_path()):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert sorted(p.name for p in store.key_path().parent.iterdir()) == [
        "anthropic_api_key",
        "anthropic_api_key.json",
    ]


def test_save_refuses_a_non_key_and_keeps_the_old_one() -> None:
    store.save(KEY, D1, D2)
    with pytest.raises(ValueError, match="not an Anthropic API key"):
        store.save("hello", D1, D2)
    assert store.read_key() == KEY


def test_save_replaces_an_old_key() -> None:
    store.save(KEY, D1, D2)
    store.save(OTHER, D2, date(2027, 1, 1))
    assert store.read_key() == OTHER


@pytest.mark.parametrize(
    "text",
    [
        "",
        "{",
        "[]",
        '{"created": "2026-11-01"}',
        '{"created": "x", "expires": "y"}',
        '{"created": 1, "expires": 2}',
    ],
)
def test_read_meta_bad_files_are_none(text: str) -> None:
    store.meta_path().parent.mkdir(parents=True)
    store.meta_path().write_text(text)
    assert store.read_meta() is None


def test_read_meta_missing_is_none() -> None:
    assert store.read_meta() is None

"""The paired-device list: hashes only, mode 0600, last_seen touched at most once an hour."""

import json
import stat
from pathlib import Path

import pytest
from todoimpl.http.devices_store import DeviceStore, default_path, digest


class Clock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(tmp_path: Path, clock: Clock) -> DeviceStore:
    return DeviceStore(tmp_path / "cfg" / "devices.json", clock)


def entries(store: DeviceStore) -> list[dict[str, object]]:
    data: list[dict[str, object]] = json.loads(store.path.read_text(encoding="utf-8"))
    return data


def test_default_path_follows_the_env_then_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TODOIMPL_DEVICES", str(tmp_path / "d.json"))
    assert default_path() == tmp_path / "d.json"
    monkeypatch.delenv("TODOIMPL_DEVICES")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_path() == tmp_path / ".config" / "todoImplementer" / "devices.json"


def test_add_stores_only_the_hash_with_mode_0600(store: DeviceStore) -> None:
    store.add("raw-secret-token", "Mozilla/5.0 " + "x" * 200)
    text = store.path.read_text(encoding="utf-8")
    assert "raw-secret-token" not in text
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    (entry,) = entries(store)
    assert entry == {
        "sha256": digest("raw-secret-token"),
        "created": 1_000_000,
        "last_seen": 1_000_000,
        "ua": ("Mozilla/5.0 " + "x" * 200)[:80],
    }


def test_missing_user_agent_is_empty(store: DeviceStore) -> None:
    store.add("t", None)
    assert entries(store)[0]["ua"] == ""


def test_check_knows_added_tokens_only(store: DeviceStore) -> None:
    store.add("one", "a")
    store.add("two", "b")
    assert store.check("one")
    assert store.check("two")
    assert not store.check("three")
    assert not store.check("")


def test_missing_file_means_nobody_is_paired(store: DeviceStore) -> None:
    assert not store.check("anything")


def test_deleting_the_file_revokes_everyone(store: DeviceStore) -> None:
    store.add("one", "a")
    store.path.unlink()
    assert not store.check("one")


@pytest.mark.parametrize("junk", ["not json", "{}", '["x"]', '[{"sha256": 1}]', "[1]", '[{"nope": 1}]'])
def test_a_damaged_file_fails_closed(store: DeviceStore, junk: str) -> None:
    store.path.parent.mkdir(parents=True)
    store.path.write_text(junk, encoding="utf-8")
    assert not store.check("one")
    store.add("one", "a")  # pairing a new phone repairs the file
    assert store.check("one")


def test_last_seen_moves_at_most_once_an_hour(store: DeviceStore, clock: Clock) -> None:
    store.add("one", "a")
    clock.now += 3599
    assert store.check("one")
    assert entries(store)[0]["last_seen"] == 1_000_000
    clock.now += 1
    assert store.check("one")
    assert entries(store)[0]["last_seen"] == 1_003_600
    assert entries(store)[0]["created"] == 1_000_000


def test_overlong_tokens_are_refused_without_hashing_work(store: DeviceStore) -> None:
    store.add("one", "a")
    assert not store.check("x" * 5000)

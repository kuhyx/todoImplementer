"""scripts/rotate_api_key.py: hidden paste first, clipboard fallback, verify live, never clobber a valid key.

Everything is fake: no xclip, no browser, no network, fake keys in a temp HOME.
"""

from datetime import date, timedelta
from pathlib import Path

import pytest
import rotate_api_key as rot
from todoimpl.apikey import store

KEY = "sk-ant-api03-" + "A" * 90
NEW = "sk-ant-api03-" + "N" * 90
NEWER = "sk-ant-usr01-" + "M" * 40
TODAY = date(2026, 11, 8)


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("TODOIMPL_APIKEY", raising=False)


class World:
    """Scripted answers: `typed` for the hidden prompt, `clip` for successive clipboard reads."""

    def __init__(self, typed: list[str] | None = None, clip: list[str | None] | None = None) -> None:
        self.typed, self.clip = list(typed or []), list(clip or [])
        self.answers: list[str] = []
        self.said: list[str] = []
        self.opened: list[str] = []
        self.cleared = 0
        self.now = 0.0
        self.replies: list[tuple[int, str]] = []
        self.sent: list[str] = []

    def transport(self, _url: str, headers: dict[str, str], _timeout: float) -> tuple[int, str]:
        self.sent.append(headers["x-api-key"])
        return self.replies.pop(0) if self.replies else (200, "{}")

    def read_secret(self, prompt: str) -> str:
        self.said.append(f"PROMPT {prompt}")
        return self.typed.pop(0)

    def read_clipboard(self) -> str | None:
        return self.clip.pop(0) if self.clip else ""

    def ask(self, prompt: str) -> str:
        self.said.append(f"ASK {prompt}")
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def io(self) -> rot.Io:
        return rot.Io(
            open_url=self.opened.append,
            read_secret=self.read_secret,
            read_clipboard=self.read_clipboard,
            clear_clipboard=lambda: setattr(self, "cleared", self.cleared + 1),
            ask=self.ask,
            sleep=self.sleep,
            monotonic=lambda: self.now,
            today=lambda: TODAY,
            transport=self.transport,
            say=self.said.append,
        )

    def run(self, *args: str) -> int:
        return rot.main(list(args), self.io())

    @property
    def text(self) -> str:
        return "\n".join(self.said)


def test_typed_key_is_verified_then_saved_with_30_day_expiry() -> None:
    world = World(typed=[f" {NEW}\n"])
    assert world.run() == 0
    assert store.read_key() == NEW
    meta = store.read_meta()
    assert meta is not None
    assert (meta.created, meta.expires) == (TODAY, TODAY + timedelta(days=30))
    assert world.sent == [NEW]
    assert world.cleared == 1
    assert f"saved, expires {TODAY + timedelta(days=30)}" in world.text
    assert NEW not in world.text


def test_opens_the_keys_page_unless_told_not_to() -> None:
    world = World(typed=[NEW])
    world.run()
    assert world.opened == ["https://platform.claude.com/settings/keys"]
    other = World(typed=[NEW])
    other.run("--no-open")
    assert other.opened == []
    assert "30-day expiry" in other.text
    assert "hidden" in other.text


def test_days_flag_sets_the_expiry() -> None:
    World(typed=[NEW]).run("--days", "7")
    meta = store.read_meta()
    assert meta is not None
    assert meta.expires == TODAY + timedelta(days=7)


def test_empty_prompt_falls_back_to_the_clipboard() -> None:
    world = World(typed=[""], clip=["", "just text", NEW])
    assert world.run("--no-open") == 0
    assert store.read_key() == NEW
    assert "clipboard" in world.text


def test_clipboard_fallback_ignores_the_stored_key_until_a_new_one_appears() -> None:
    store.save(KEY, TODAY - timedelta(days=29), TODAY + timedelta(days=1))
    world = World(typed=[""], clip=[KEY, KEY, NEW])
    assert world.run() == 0
    assert store.read_key() == NEW
    assert world.sent == [NEW]


def test_clipboard_timeout_asks_retry_or_skip_and_skip_keeps_the_old_key() -> None:
    store.save(KEY, TODAY, TODAY + timedelta(days=30))
    world = World(typed=[""], clip=[])
    world.answers = ["skip"]
    assert world.run() == 1
    assert store.read_key() == KEY
    assert world.now >= 600
    assert "timed out" in world.text


def test_unavailable_clipboard_is_reported_not_polled_for_ten_minutes() -> None:
    world = World(typed=[""], clip=[None])
    world.answers = ["s"]
    assert world.run() == 1
    assert world.now < 5
    assert "xclip" in world.text


def test_a_non_key_typed_is_refused_and_never_stored() -> None:
    store.save(KEY, TODAY, TODAY + timedelta(days=30))
    world = World(typed=["hello world", NEW])
    world.answers = ["retry"]
    assert world.run() == 0
    assert "not an API key" in world.text
    assert world.sent == [NEW]  # junk never even reached the network
    assert store.read_key() == NEW


def test_typing_the_stored_key_again_is_refused() -> None:
    store.save(KEY, TODAY, TODAY + timedelta(days=30))
    world = World(typed=[KEY])
    assert world.run() == 1  # no answers left: EOF means skip
    assert "already stored" in world.text
    assert world.sent == []


def test_failed_verify_loops_on_retry_and_never_advances() -> None:
    store.save(KEY, TODAY, TODAY + timedelta(days=30))
    world = World(typed=[NEW, NEWER])
    world.replies = [(401, "")]
    world.answers = ["retry"]
    assert world.run() == 0
    assert world.sent == [NEW, NEWER]
    assert store.read_key() == NEWER
    assert "rejected" in world.text


def test_a_failed_verify_never_clobbers_a_valid_stored_key() -> None:
    store.save(KEY, TODAY, TODAY + timedelta(days=30))
    world = World(typed=[NEW])
    world.replies = [(401, "")]
    world.answers = ["skip"]
    assert world.run() == 1
    assert store.read_key() == KEY
    assert world.cleared == 0


def test_network_failure_retry_reverifies_the_same_clipboard_key() -> None:
    world = World(typed=["", ""], clip=[NEW, NEW])
    world.replies = [(500, "")]
    world.answers = ["r"]
    assert world.run() == 0
    assert world.sent == [NEW, NEW]  # a network error is not the key's fault, so it may be tried again
    assert "could not check" in world.text


def test_a_rejected_clipboard_key_is_not_tried_again() -> None:
    world = World(typed=["", ""], clip=[NEW, NEW, NEWER])
    world.replies = [(401, "")]
    world.answers = ["retry"]
    assert world.run() == 0
    assert world.sent == [NEW, NEWER]


def test_answers_other_than_retry_or_skip_are_asked_again() -> None:
    world = World(typed=[NEW, NEWER])
    world.replies = [(401, "")]
    world.answers = ["what", "", "retry"]
    assert world.run() == 0
    assert world.text.count("ASK retry / skip? ") == 3


def test_eof_on_the_tty_means_skip() -> None:
    world = World(typed=[NEW])
    world.replies = [(401, "")]
    assert world.run() == 1

#!/usr/bin/env python3
"""Rotate the Claude Console API key: paste the new one (hidden), verify it live, save it, 30-day expiry.

Run it in a terminal when the board says the key is expired, invalid or missing. The key is read with a hidden
prompt (the X clipboard is unreliable on this machine); an empty answer falls back to watching the clipboard
for up to 10 minutes. Nothing is saved until the key is shaped right, differs from the stored one and passes
the live check, so a good stored key is never replaced by junk. The key is never printed.
"""

import argparse
import getpass
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

from todoimpl.apikey import store
from todoimpl.apikey.verify import Transport, urllib_transport, verify

KEYS_URL = "https://platform.claude.com/settings/keys"
PROMPT = "paste the new key (hidden): "
WAIT_SECONDS = 600.0
CLIPBOARD = ["xclip", "-o", "-selection", "clipboard"]


@dataclass(frozen=True)
class Io:
    """Every side effect, so tests inject fakes (no browser, clipboard, TTY, clock or network)."""

    open_url: Callable[[str], None]
    read_secret: Callable[[str], str]
    read_clipboard: Callable[[], str | None]  # None: no clipboard tool at all
    clear_clipboard: Callable[[], None]
    ask: Callable[[str], str]
    sleep: Callable[[float], None]
    monotonic: Callable[[], float]
    today: Callable[[], date]
    transport: Transport
    say: Callable[[str], None]


def open_url(url: str) -> None:
    """Open url with xdg-open, detached; a missing tool is fine, the instruction line names the URL."""
    try:
        subprocess.Popen(  # noqa: S603 - fixed argv
            ["xdg-open", url],  # noqa: S607
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return


def read_clipboard() -> str | None:
    """Return the clipboard text; "" when empty or unreadable, None when xclip is not installed."""
    if shutil.which("xclip") is None:
        return None
    try:
        done = subprocess.run(CLIPBOARD, capture_output=True, timeout=5, check=False)  # noqa: S603
    except OSError, subprocess.TimeoutExpired:
        return ""
    return done.stdout.decode("utf-8", "replace") if done.returncode == 0 else ""


def clear_clipboard() -> None:
    """Empty the clipboard so the key does not linger; a missing xclip is fine."""
    try:
        subprocess.run(
            ["xclip", "-selection", "clipboard"],  # noqa: S607
            input=b"",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return


def input_line(prompt: str) -> str:
    """Read one line from the TTY (looked up at call time, so tests can replace input)."""
    return input(prompt)


def real_io() -> Io:
    """Wire the real browser opener, hidden prompt, xclip, TTY, clock, network and stdout."""
    return Io(
        open_url,
        getpass.getpass,
        read_clipboard,
        clear_clipboard,
        input_line,
        time.sleep,
        time.monotonic,
        date.today,
        urllib_transport,
        print,
    )


def _from_clipboard(io: Io, ignore: set[str]) -> tuple[str | None, str]:
    """Poll the clipboard once a second for a new key; (key, "") or (None, why)."""
    io.say("empty: watching the clipboard for a new key (up to 10 min)")
    deadline = io.monotonic() + WAIT_SECONDS
    while io.monotonic() < deadline:
        text = io.read_clipboard()
        if text is None:
            return None, "clipboard unavailable (xclip is not installed)"
        text = text.strip()
        if store.is_key(text) and text not in ignore:
            return text, ""
        io.sleep(1.0)
    return None, "timed out waiting for a new key on the clipboard"


def candidate(io: Io, ignore: set[str]) -> tuple[str | None, str]:
    """Return the next key to try (hidden prompt, else clipboard) as (key, ""), or (None, why)."""
    typed = io.read_secret(PROMPT).strip()
    if not typed:
        return _from_clipboard(io, ignore)
    if not store.is_key(typed):
        return None, "that is not an API key (expected sk-ant-...)"
    if typed in ignore:
        return None, "that key is already stored or was already rejected"
    return typed, ""


def retry_or_skip(io: Io) -> bool:
    """Return True to retry, False to skip; anything else is asked again, a closed TTY means skip."""
    while True:
        try:
            answer = io.ask("retry / skip? ").strip().lower()
        except EOFError:
            return False
        if answer[:1] in ("r", "s"):
            return answer[0] == "r"


def rotate(io: Io, days: int, *, no_open: bool) -> int:
    """Loop until a key verifies and is saved (0) or kuhy skips (1); a failure never advances."""
    ignore = {key} if (key := store.read_key()) else set()
    if not no_open:
        io.open_url(KEYS_URL)
    io.say(f"Create a key at {KEYS_URL} with a 30-day expiry, copy it, paste it at the hidden prompt.")
    while True:
        key, problem = candidate(io, ignore)
        if key is not None:
            verdict = verify(key, io.transport)
            if verdict.outcome == "valid":
                today = io.today()
                store.save(key, today, today + timedelta(days=days))
                io.clear_clipboard()
                io.say(f"saved, expires {today + timedelta(days=days)}")
                return 0
            if verdict.outcome == "invalid":
                ignore.add(key)
                problem = f"the API rejected that key ({verdict.detail})"
            else:
                problem = f"could not check the key: {verdict.detail}"
        io.say(problem)
        if not retry_or_skip(io):
            io.say("skipped: the stored key is unchanged")
            return 1


def main(argv: list[str] | None = None, io: Io | None = None) -> int:
    """Parse flags and run the rotation; exit 0 saved, 1 skipped."""
    parser = argparse.ArgumentParser(prog="rotate_api_key.py", description=__doc__)
    parser.add_argument("--no-open", action="store_true", help="do not open the Console keys page")
    parser.add_argument("--days", type=int, default=30, help="days until the new key expires (default 30)")
    args = parser.parse_args(argv)
    return rotate(io or real_io(), args.days, no_open=args.no_open)


if __name__ == "__main__":
    sys.exit(main())

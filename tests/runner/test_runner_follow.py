"""Following a turn's files: the tail, lost hosts, legacy records and abandoning a recorded turn."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path

import pytest
from adoptfakes import STEM, result, rig, text
from runnerfakes import Env
from schedfakes import wait
from todoimpl.runner import adopt, claude, files, launch, orphans
from todoimpl.runner.stream import StreamParser


def test_follow_waits_for_the_rest_of_a_partial_line_and_publishes_only_past_the_fed_offset(
    tmp_path: Path,
) -> None:
    first, second, final = text("one"), text("two"), result("D: done")
    stem_stream = tmp_path / f"{STEM}.stream.jsonl"
    me = os.getpid()
    rec = orphans.Record(stem=STEM, role="implement", host_pid=me, host_start=orphans.start_of(me))
    stem_stream.write_bytes(first + second[:20])
    files.write_json(tmp_path / f"{STEM}.fed", len(first))  # the previous server showed line one
    seen: list[tuple[str, str]] = []

    def finish() -> None:
        time.sleep(0.2)
        with stem_stream.open("ab") as out:
            out.write(second[20:] + final + b'{"type": "assistant"')  # ends without a newline
        files.write_json(tmp_path / f"{STEM}.exit.json", {"code": 7})

    threading.Thread(target=finish).start()
    parser = StreamParser()
    code = adopt.follow(tmp_path, rec, parser, lambda k, t, _tool: seen.append((k, t)), threading.Event())
    assert code == 7
    assert seen == [("text", "two"), ("result", "D: done")]  # line one replayed silently, nothing doubled
    assert parser.result.finished
    assert files.read_json(tmp_path / f"{STEM}.fed") == len(first + second + final)


def test_follow_lets_go_when_the_server_closes(tmp_path: Path) -> None:
    detach = threading.Event()
    detach.set()
    with pytest.raises(adopt.Detached):
        adopt.follow(tmp_path, orphans.Record(stem=STEM), StreamParser(), lambda *_a: None, detach)


def test_a_host_that_is_gone_without_an_exit_record_means_the_turn_is_lost(tmp_path: Path) -> None:
    gone = orphans.Record(stem=STEM, role="plan", host_pid=2**22 + 1, host_start="1")
    assert adopt.follow(tmp_path, gone, StreamParser(), lambda *_a: None, threading.Event()) is None
    stale = orphans.Record(stem=STEM, role="plan", launched=1.0)  # launched ages ago, never recorded a host
    assert adopt.follow(tmp_path, stale, StreamParser(), lambda *_a: None, threading.Event()) is None


def test_a_host_that_is_still_starting_is_waited_for(tmp_path: Path) -> None:
    starting = orphans.Record(stem=STEM, role="plan", launched=time.time())
    threading.Timer(0.2, files.write_json, (tmp_path / f"{STEM}.exit.json", {"code": 0})).start()
    assert adopt.follow(tmp_path, starting, StreamParser(), lambda *_a: None, threading.Event()) == 0


def test_an_exit_record_written_as_the_host_dies_is_not_a_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def dying(run_dir: Path, rec: orphans.Record) -> bool:
        files.write_json(run_dir / f"{STEM}.exit.json", {"code": 3})
        return False

    monkeypatch.setattr(adopt, "host_alive", dying)
    got = adopt.follow(
        tmp_path, orphans.Record(stem=STEM), StreamParser(), lambda *_a: None, threading.Event()
    )
    assert got == 3


def test_reap_legacy_kills_only_a_record_without_a_stem(tmp_path: Path) -> None:
    adopt.reap_legacy(tmp_path)  # no record
    orphans.begin(tmp_path, STEM, "plan", None)
    adopt.reap_legacy(tmp_path)  # a stemmed record belongs to a host, not to the reaper
    assert orphans.read(tmp_path) is not None
    old = subprocess.Popen(["sleep", "30"], start_new_session=True)
    orphans.record(tmp_path, old.pid)
    adopt.reap_legacy(tmp_path)
    assert old.wait(timeout=10) < 0
    assert orphans.read(tmp_path) is None


def test_abandon_stops_whatever_turn_is_recorded(world: Env, tmp_path: Path) -> None:
    adopt.abandon(tmp_path)  # nothing recorded
    old = subprocess.Popen(["sleep", "30"], start_new_session=True)
    orphans.record(tmp_path, old.pid)
    adopt.abandon(tmp_path)
    assert old.wait(timeout=10) < 0
    run_dir, wt = rig(world, tmp_path)
    world.script("abcd1234", {"_fake": "sleep", "sec": 30})
    launch.start(run_dir, STEM, "implement", claude.build("implement", "go", wt))
    wait(lambda: (orphans.read(run_dir) or orphans.Record()).pid is not None)
    live = orphans.read(run_dir)
    assert live is not None
    adopt.abandon(run_dir)
    assert orphans.read(run_dir) is None
    wait(lambda: not orphans.alive(live.pid, live.start))

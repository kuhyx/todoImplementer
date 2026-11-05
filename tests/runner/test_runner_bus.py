import threading
from pathlib import Path

from todoimpl.runner.bus import Bus


def _activity(text: str) -> dict[str, object]:
    return {"type": "activity", "at": 1.0, "kind": "text", "text": text, "tool": None}


def test_activity_gets_a_persisted_seq_and_replays_after_it(tmp_path: Path) -> None:
    bus = Bus(tmp_path)
    bus.publish("abcd1234", _activity("one"))
    bus.publish("abcd1234", {"type": "cost", "cost_usd": 0.5})
    bus.publish("abcd1234", _activity("two"))
    again = Bus(tmp_path)
    again.publish("abcd1234", _activity("three"))
    events = again.subscribe("abcd1234", after=1)
    assert [next(events)["text"] for _ in range(2)] == ["two", "three"]
    again.close()
    assert list(events) == []
    (tmp_path / "abcd1234" / "events.jsonl").write_text('{"seq": 7}\n{"torn\n', encoding="utf-8")
    third = Bus(tmp_path)
    third.publish("abcd1234", _activity("four"))
    assert third.history("abcd1234", 7)[0]["seq"] == 8
    assert Bus(tmp_path).history("none0000", 0) == []


def test_live_subscribers_get_every_event(tmp_path: Path) -> None:
    bus = Bus(tmp_path)
    events = bus.subscribe("abcd1234")
    got: list[dict[str, object]] = []
    ready = threading.Event()

    def reader() -> None:
        ready.set()
        got.extend(events)

    thread = threading.Thread(target=reader)
    thread.start()
    ready.wait()
    while not bus.subscribers("abcd1234"):
        threading.Event().wait(0.01)
    bus.publish("abcd1234", {"type": "stage", "stage": "plan"})
    bus.publish("other000", {"type": "stage", "stage": "plan"})
    bus.close()
    thread.join(5)
    assert got == [{"type": "stage", "stage": "plan"}]
    assert bus.subscribers("abcd1234") == 0

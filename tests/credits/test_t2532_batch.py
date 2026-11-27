"""T2532: background one-shots go through the Message Batches API on the free credits (half price).

A fake transport stands in for api.anthropic.com: no network. `root` is the ready credits root (conftest).
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest
from todoimpl.credits import batch, batchstore, ledger, marks, setting
from todoimpl.runner import batchshot, oneshot

if TYPE_CHECKING:
    from pathlib import Path

NOW = 1_800_000_000.0
USAGE = {"input_tokens": 1_000_000, "output_tokens": 100_000}


class BoomError(Exception):
    """The caller's error type."""


class FakeApi:
    """Batches endpoints: create, retrieve, results; records every call."""

    def __init__(self, result: str = "succeeded", create_status: int = 200, create_body: str = "") -> None:
        self.calls: list[tuple[str, str, dict[str, str], bytes | None]] = []
        self.status = "in_progress"
        self.result = result
        self.create = (create_status, create_body)
        self.custom_id = ""

    def __call__(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float
    ) -> tuple[int, str]:
        assert timeout <= batch.TIMEOUT_S
        self.calls.append((method, url, headers, body))
        if method == "POST":
            self.custom_id = json.loads(body or b"{}")["requests"][0]["custom_id"]
            return self.create[0], self.create[1] or json.dumps(
                {"id": "msgbatch_1", "processing_status": "in_progress"}
            )
        if url.endswith("/results"):
            if self.result == "succeeded":
                inner = {
                    "type": "succeeded",
                    "message": {
                        "content": [
                            {"type": "thinking", "thinking": ""},
                            {"type": "text", "text": '{"ok": 1}'},
                        ],
                        "usage": USAGE,
                    },
                }
            else:
                inner = {"type": self.result, "error": {"type": "x"}}
            return 200, json.dumps({"custom_id": self.custom_id, "result": inner}) + "\n"
        return 200, json.dumps(
            {"id": "msgbatch_1", "processing_status": self.status, "results_url": url + "/results"}
        )


def _run(root: Path, api: FakeApi, now: float = NOW, fallback: list[str] | None = None) -> str:
    calls = fallback if fallback is not None else []

    def plan() -> str:
        calls.append("plan")
        return "plan text"

    return batchshot.run(
        "classify this",
        model="haiku",
        kind="triage",
        root=root,
        error=BoomError,
        fallback=plan,
        now=now,
        transport=api,
    )


def test_t2532_submit_then_pending_then_result_at_half_price(root: Path) -> None:
    api = FakeApi()
    with pytest.raises(BoomError, match="batch pending"):
        _run(root, api)
    method, url, headers, body = api.calls[0]
    assert (method, url) == ("POST", batch.API)
    assert headers["x-api-key"].startswith("sk-ant-api03-")
    params = json.loads(body or b"{}")["requests"][0]["params"]
    assert params["model"] == "claude-haiku-5-5"
    assert params["output_config"] == {"effort": "low"}
    assert "temperature" not in params
    assert [r["kind"] for r in batchstore.pending(root)] == ["triage"]
    with pytest.raises(BoomError, match="batch pending"):  # polled too soon: no call
        _run(root, api, NOW + 1)
    assert len(api.calls) == 1
    api.status = "ended"
    assert _run(root, api, NOW + batch.POLL_S) == '{"ok": 1}'
    assert batchstore.pending(root) == []
    # Haiku 5.5: $0.10 in + $0.05 out per this usage, at half price
    assert ledger.spent(root, 0, "batch") == pytest.approx((0.10 + 0.05) * 0.5)


def test_t2532_errored_batch_falls_back_to_the_plan(root: Path) -> None:
    api = FakeApi(result="errored")
    with pytest.raises(BoomError):
        _run(root, api)
    api.status = "ended"
    seen: list[str] = []
    assert _run(root, api, NOW + batch.POLL_S, seen) == "plan text"
    assert seen == ["plan"]
    assert batchstore.pending(root) == []


def test_t2532_purchased_credit_refuses_every_batch(root: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = setting.settings_path()
    data = json.loads(path.read_text())
    path.write_text(json.dumps({**data, "credits_purchased_usd": 5}))
    api, seen = FakeApi(), list[str]()
    assert _run(root, api, fallback=seen) == "plan text"
    assert api.calls == []
    assert seen == ["plan"]
    assert "purchased" in caplog.text


def test_t2532_credits_not_ready_never_batch(root: Path) -> None:
    marks.mark_exhausted(root, NOW + 3600, "test")
    api, seen = FakeApi(), list[str]()
    assert _run(root, api, fallback=seen) == "plan text"
    assert api.calls == []


def test_t2532_billing_error_marks_exhausted_and_falls_back(root: Path) -> None:
    body = json.dumps(
        {"type": "error", "error": {"type": "billing_error", "message": "credit balance is too low"}}
    )
    api, seen = FakeApi(create_status=400, create_body=body), list[str]()
    assert _run(root, api, fallback=seen) == "plan text"
    assert marks.exhausted(root, NOW)
    assert batchstore.pending(root) == []


def test_t2532_oneshot_batch_flag_routes_through_batchshot(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(batch, "TRANSPORT", FakeApi())
    with pytest.raises(BoomError, match="batch pending"):
        oneshot.run("p", model="haiku", kind="merge", root=root, timeout=5, error=BoomError, batch=True)


def test_t2532_pending_batches_show_in_the_credits_view_and_pace(root: Path) -> None:
    from todoimpl.credits import pacing, route  # noqa: PLC0415

    with pytest.raises(BoomError):
        _run(root, FakeApi())
    view = route.view(root, NOW + 60)["batches"]
    assert view == {"pending": 1, "est_usd": batchshot.EST_USD, "oldest_at": NOW}
    assert pacing.pace(root, NOW + 60).reserved_usd == pytest.approx(batchshot.EST_USD)
    assert batchstore.view(root, NOW + batchstore.MAX_AGE_S)["pending"] == 0


def test_t2532_old_batch_past_a_day_goes_to_the_plan(root: Path) -> None:
    api = FakeApi()
    with pytest.raises(BoomError):
        _run(root, api)
    seen: list[str] = []
    assert _run(root, api, NOW + batchstore.MAX_AGE_S, seen) == "plan text"
    assert batchstore.pending(root) == []


def test_t2532_network_failure_goes_to_the_plan(root: Path) -> None:
    def down(*_args: object) -> tuple[int, str]:
        raise OSError("no route")

    out = batchshot.run(
        "p",
        model="haiku",
        kind="triage",
        root=root,
        error=BoomError,
        fallback=lambda: "plan",
        now=NOW,
        transport=down,
    )
    assert out == "plan"


def _send(status: int, text: str) -> batch.Transport:
    return lambda *_a: (status, text)


@pytest.mark.parametrize(
    ("status", "text", "why"),
    [(500, "overloaded", "answered 500"), (200, "not json", "no JSON"), (200, "[1]", "no id")],
)
def test_t2532_bad_create_replies_raise(root: Path, status: int, text: str, why: str) -> None:
    with pytest.raises(batch.BatchError, match=why):
        batch.submit(root, "c", "p", "haiku", _send(status, text))
    assert not marks.exhausted(root, NOW)


def test_t2532_no_key_raises(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIMPL_APIKEY", str(root / "absent"))
    with pytest.raises(batch.BatchError, match="no API key"):
        batch.retrieve(root, "b", _send(200, "{}"))


def test_t2532_replies_of_odd_shape(root: Path) -> None:
    assert batch.retrieve(root, "b", _send(200, "[]")) == {}
    lines = "\n" + json.dumps({"custom_id": "other"}) + "\n[2]\n"
    assert batch.result(root, "u", "mine", _send(200, lines)) == ("missing", "", {})
    assert batch.model_id("claude-opus-5-5") == "claude-opus-5-5"


def test_t2532_still_running_stays_pending(root: Path) -> None:
    api = FakeApi()
    with pytest.raises(BoomError):
        _run(root, api)
    with pytest.raises(BoomError, match="batch pending for 1 min"):
        _run(root, api, NOW + batch.POLL_S)
    assert batchstore.pending(root)[0]["polled_at"] == NOW + batch.POLL_S


def test_t2532_a_bad_purchased_value_counts_as_purchased(root: Path) -> None:
    path = setting.settings_path()
    path.write_text(json.dumps({**json.loads(path.read_text()), "credits_purchased_usd": "lots"}))
    assert setting.purchased_usd() == 1.0


def test_t2532_oneshot_plan_fallback_runs_claude_p(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, json.dumps({"result": "plan text", "is_error": False}), ""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(batchshot, "run", lambda *_a, fallback, **_k: fallback())
    out = oneshot.run("p", model="haiku", kind="merge", root=root, timeout=5, error=BoomError, batch=True)
    assert out == "plan text"
    assert "-p" in seen[0]

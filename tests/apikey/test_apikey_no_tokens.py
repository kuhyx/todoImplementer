"""The hourly key check never spends tokens: one bodiless GET /v1/models, no model call, no claude."""

import urllib.request
from pathlib import Path
from typing import Any, Self

import pytest
from todoimpl.apikey import verify as verify_mod

PACKAGE = Path(verify_mod.__file__).resolve().parent
FAKE_KEY = "sk-ant-usr01-" + "x" * 40


class _Reply:
    status = 200

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, _n: int) -> bytes:
        return b'{"data": []}'


def test_live_check_is_a_bodiless_get_of_the_models_list(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, **_: Any) -> _Reply:
        sent.append(request)
        return _Reply()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert verify_mod.verify(FAKE_KEY).outcome == "valid"
    assert len(sent) == 1
    assert (sent[0].get_method(), sent[0].full_url, sent[0].data) == ("GET", verify_mod.MODELS_URL, None)
    assert verify_mod.MODELS_URL == "https://api.anthropic.com/v1/models"


@pytest.mark.parametrize(
    "billed", ["/v1/messages", "count_tokens", "claude_bin", "claude-agent-sdk", "query("]
)
def test_key_package_has_no_token_spending_call(billed: str) -> None:
    offenders = [p.name for p in PACKAGE.glob("*.py") if billed in p.read_text(encoding="utf-8")]
    assert offenders == []

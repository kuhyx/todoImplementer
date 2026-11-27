"""The sandbox board's free credits (T2532 checks): a scratch key, the local fake API, the purchased value.

The scratch HOME gets no key until `sandbox.py credits on`, so the credits stay unavailable by default (the
free-route checks need that). The server always talks to `fake_batches.py`, never to api.anthropic.com.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from e2e_procs import launch, tail, wait_for
from e2e_world import PYTHON, State

HERE = Path(__file__).resolve().parent
FAKE_KEY = "sk-ant-api03-" + "S" * 90  # shaped like a key, accepted only by the local fake


def _url(work: Path) -> str:
    return str(json.loads((work / "batches.json").read_text(encoding="utf-8"))["url"])


def start_fake(state: State, delay: float = 30.0) -> None:
    """Start the fake API (a batch ends `delay` s after it was made, so the loader shows)."""
    work, out = state.path, state.path / "batches.json"
    argv = [
        PYTHON,
        str(HERE / "fake_batches.py"),
        str(out),
        str(work / "artifacts" / "batches.jsonl"),
        str(delay),
    ]
    state.handles["batches"] = launch("batches", argv, {}, work / "home", work / "artifacts" / "batches.log")
    if not wait_for(out.exists, 15):
        sys.exit("fake batches API did not start:\n" + tail(work / "artifacts" / "batches.log"))


def env(work: Path) -> dict[str, str]:
    """Server env that points the key check and the Batches API at the fake."""
    if not (work / "batches.json").exists():
        return {}
    base = _url(work)
    return {
        "TODOIMPL_BATCH_URL": f"{base}/v1/messages/batches",
        "TODOIMPL_MODELS_URL": f"{base}/v1/models",
        "TODOIMPL_SDK_PYTHON": PYTHON,
    }


def set_credits(work: Path, arg: str, purchased: float = 0.0) -> None:
    """`on`: write the scratch key and `credits_purchased_usd`; `off`: remove the key."""
    config = work / "home" / ".config" / "todoImplementer"
    config.mkdir(parents=True, exist_ok=True)
    key = config / "anthropic_api_key"
    if arg == "off":
        key.unlink(missing_ok=True)
        print("credits off (no key)")
        return
    key.write_text(FAKE_KEY + "\n", encoding="utf-8")
    key.chmod(0o600)
    settings = config / "settings.json"
    data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
    settings.write_text(json.dumps({**data, "credits_purchased_usd": purchased}), encoding="utf-8")
    print(f"credits on (scratch key, purchased ${purchased:g})")

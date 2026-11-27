"""A background one-shot through the Batches API (T2532), else the plan's `claude -p` (`fallback`).

No callback and no poller thread: the callers (the triage tick, the merge refresh) already retry a failed
one-shot after their interval with the same prompt. The first call submits and raises `error("batch
pending")`; a later call polls (at most once a minute) and returns the text once the batch has ended. An
errored, expired or cancelled batch, or any batch call that fails, goes to `fallback` at once. The spend lands
in the credit ledger as route `batch` at half the list price, and counts in the week's pace.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

from todoimpl.credits import batch, batchstore, ledger, prices

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

log = logging.getLogger(__name__)

PENDING = "batch pending"
EST_USD = 0.01  # what a pending one-shot counts for in the pace: Haiku at half price, a few K tokens


def _pending(error: type[Exception], since: float, now: float) -> Exception:
    return error(f"{PENDING} for {max(0, int(now - since)) // 60} min (Batches API, half price)")


def failed_at(now: float, exc: Exception, retry_s: float) -> float:
    """Return when a failed one-shot counts as failed: a pending batch is asked again after `POLL_S`."""
    return now - (retry_s - batch.POLL_S) if PENDING in str(exc) else now


def run(  # noqa: PLR0913 - one call, keyword-only
    prompt: str,
    *,
    model: str,
    kind: str,
    root: Path,
    error: type[Exception],
    fallback: Callable[[], str],
    now: float | None = None,
    transport: batch.Transport | None = None,
) -> str:
    """Return the batch's text, raise `error` while it is pending, or return `fallback()`."""
    at = time.time() if now is None else now
    send = transport or batch.TRANSPORT
    name = batchstore.key(kind, prompt)
    row = batchstore.get(root, name)
    try:
        if row is None:
            if (why := batch.refusal(root, at)) is not None:
                log.info("%s one-shot on the plan: %s", kind, why)
                return fallback()
            custom = uuid.uuid4().hex[:16]
            found = batch.submit(root, custom, prompt, model, send, at)
            row = {"id": found, "custom_id": custom, "kind": kind, "model": model, "submitted_at": at,
                   "polled_at": at, "est_usd": EST_USD}  # fmt: skip
            batchstore.put(root, name, row)
            raise _pending(error, at, at)
        if at - float(row["submitted_at"]) >= batchstore.MAX_AGE_S:
            batchstore.drop(root, name)
            return fallback()
        if at - float(row["polled_at"]) < batch.POLL_S:
            raise _pending(error, float(row["submitted_at"]), at)
        state = batch.retrieve(root, str(row["id"]), send)
        if state.get("processing_status") != "ended":
            batchstore.put(root, name, {**row, "polled_at": at})
            raise _pending(error, float(row["submitted_at"]), at)
        kind_of, text, usage = batch.result(root, str(state.get("results_url")), str(row["custom_id"]), send)
    except batch.BatchError as exc:
        log.warning("%s batch failed, on the plan instead: %s", kind, exc)
        batchstore.drop(root, name)
        return fallback()
    batchstore.drop(root, name)
    if kind_of != "succeeded" or not text:
        log.warning("%s batch %s ended %s, on the plan instead", kind, row["id"], kind_of)
        return fallback()
    paid = prices.cost(batch.model_id(model), usage, prices.BATCH_FACTOR)
    ledger.record(
        root, task=kind, stem=f"batch-{row['id']}", role=kind, route="batch", session_id=None,
        cumulative=None, ended_at=at, estimate=paid,
    )  # fmt: skip
    return text

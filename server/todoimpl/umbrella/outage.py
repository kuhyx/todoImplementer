"""An outage pauses the round and retries on the backoff ladder; it never fails or escalates a child.

Two kinds, each with its own attempt counter in the umbrella's `extra` (cleared once the thing works again):
`network` (no route to Anthropic or a public resolver) and `gateway` (the free-model gateway answers nothing).
The raised `RetryLaterError` rests the umbrella in `paused_retry` with `retry_kind` set: the page shows why.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.runner import netwait, retry

if TYPE_CHECKING:
    from .driver import UmbrellaDriver

NET, GATEWAY = "net_retries", "gw_retries"


def _wait(d: UmbrellaDriver, counter: str, why: str, kind: str) -> retry.RetryLaterError:
    attempts = int(d.state.extra.get(counter, 0))
    d.state.extra[counter] = attempts + 1
    d.save()
    return retry.RetryLaterError(d.ctx.now() + retry.delay(attempts), why, kind)


def check_network(d: UmbrellaDriver) -> None:
    """Raise a timed retry while the internet is down; clear the counter when it is up."""
    if not netwait.online():
        raise _wait(d, NET, "offline: the round waits for the network", "network")
    d.state.extra.pop(NET, None)


def gateway_unreachable(d: UmbrellaDriver, detail: str) -> retry.RetryLaterError:
    """Return the timed retry for a gateway that answers nothing (the caller raises it)."""
    return _wait(d, GATEWAY, f"free-model gateway unreachable: {detail}", "gateway")


def gateway_ok(d: UmbrellaDriver) -> None:
    """Forget earlier failed attempts: the gateway answered."""
    d.state.extra.pop(GATEWAY, None)

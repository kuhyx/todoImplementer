"""Is the internet up? A cheap TCP connect, behind one seam so no test ever touches the network."""

from __future__ import annotations

import socket

HOSTS = (("api.anthropic.com", 443), ("1.1.1.1", 443))
TIMEOUT = 2.0


def probe() -> bool:
    """Return True when a TCP connection to Anthropic's API or to a public resolver succeeds."""
    for host in HOSTS:
        try:
            socket.create_connection(host, timeout=TIMEOUT).close()
        except OSError:
            continue
        return True
    return False


def online() -> bool:
    """Say whether the network is up (looked up at call time, so a test swaps `probe`)."""
    return probe()

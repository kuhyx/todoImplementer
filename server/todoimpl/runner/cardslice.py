"""Each card runs in its own capped slice below the board's (T2405-T2401, DOCS-resilience.md, "Resource cap").

2026-11-20: one card's SD3.5-Large render (16 GB RAM + 8 GB swap) pushed the shared `todoimpl.slice` over its
MemoryHigh, and the kernel throttled every process in it, every claude included: five running cards sat 47 min
with no activity. Now a card's turn, gate and deploy units run in `todoimpl-<card>.slice`, hard capped by the
prefix drop-in `deploy/todoimpl-.slice.d/` (no MemoryHigh anywhere: past its cap a card's biggest process is
OOM-killed instead of freezing the board). A session's own `systemd-run --slice=todoimpl.slice` job joins its
card's slice through the `systemd-run` shim (`sliceshim.sh`, keyed by `$TODOIMPL_SLICE` in the turn env), and
Cancel stops the card's whole slice, its session's jobs included.
"""

from __future__ import annotations

import re

PARENT = "todoimpl.slice"
SLICE_VAR = "TODOIMPL_SLICE"
SHIM = "systemd-run"
SHIM_SOURCE = "sliceshim.sh"
DROPIN_DIR = "todoimpl-.slice.d"
DROPIN_FILE = "50-card-cap.conf"


def card_slice(card: str) -> str:
    """`todoimpl-<card>.slice`: one dash only, so systemd nests it right below `todoimpl.slice`."""
    return "todoimpl-" + re.sub(r"[^A-Za-z0-9_]", "_", card) + ".slice"


def stop(card: str) -> None:
    """Stop everything the card runs (turn, gate, deploy, its session's jobs); tests never touch systemd."""
    from . import launch  # noqa: PLC0415 - launch imports buildlock, which imports this module

    if not launch.direct():
        launch._run(["systemctl", "--user", "stop", card_slice(card)], capture_output=True)  # noqa: SLF001

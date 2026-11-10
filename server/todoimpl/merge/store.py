"""`<run root>/merge.json`: the last classification, dismissed groups and the merges already created."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from todoimpl import atomic

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

FILE = "merge.json"
LOCK = threading.Lock()  # the worker thread and the POST handlers both write the file


@dataclass
class MergeState:
    """`ids` are the open card ids the groups were computed for (None before the first run), `at` its time."""

    ids: list[str] | None = None
    at: float = 0.0
    groups: list[dict[str, Any]] = field(default_factory=list)
    dismissed: list[str] = field(default_factory=list)
    created: dict[str, dict[str, Any]] = field(default_factory=dict)  # fingerprint -> {id, titles}
    hashes: dict[str, str] = field(default_factory=dict)  # card id -> hash of what the classifier saw of it


def _typed(data: dict[str, Any], key: str, kind: type | tuple[type, ...], default: Any) -> Any:  # noqa: ANN401 - json values
    value = data.get(key)
    return value if isinstance(value, kind) else default


class MergeStore:
    """Reads and atomically rewrites merge.json; a missing, corrupt or odd file reads as the blank state."""

    def __init__(self, root: Path) -> None:
        """`root` is the run root ($TODOIMPL_HOME)."""
        self._path = root / FILE

    def load(self) -> MergeState:
        """Return the stored state, blank where the file is absent or a field has the wrong type."""
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except OSError, ValueError:
            return MergeState()
        if not isinstance(data, dict):
            return MergeState()
        ids = _typed(data, "ids", list, None)
        return MergeState(
            ids,
            float(_typed(data, "at", (int, float), 0.0)),
            _typed(data, "groups", list, []),
            _typed(data, "dismissed", list, []),
            _typed(data, "created", dict, {}),
            _typed(data, "hashes", dict, {}),
        )

    def update(self, change: Callable[[MergeState], object]) -> None:
        """Load, apply `change` in place and write back (tmp + os.replace) under the process-wide lock."""
        with LOCK:
            state = self.load()
            change(state)
            atomic.write_text(self._path, json.dumps(vars(state), indent=1))

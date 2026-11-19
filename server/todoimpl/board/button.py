"""The button shape of a card: `Action`, the contract's action object."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    """One button; `reason` is set exactly when it is disabled."""

    id: str
    label: str
    enabled: bool = True
    reason: str | None = None
    confirm: bool = False
    value: str | None = None
    choices: tuple[dict[str, str], ...] = ()  # model only: the picker's {id, label} rows

    def to_dict(self) -> dict[str, object]:
        """Return the contract object (confirm, value and choices only when set)."""
        out: dict[str, object] = {
            "id": self.id,
            "label": self.label,
            "enabled": self.enabled,
            "reason": self.reason,
        }
        if self.confirm:
            out["confirm"] = True
        if self.value is not None:
            out["value"] = self.value
        if self.choices:
            out["choices"] = [dict(c) for c in self.choices]
        return out

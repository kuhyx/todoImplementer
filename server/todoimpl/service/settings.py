"""POST /api/settings/credits-fallback; `ServiceBackend` binds `credits_fallback` from here as its method."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from todoimpl.credits import route, setting

if TYPE_CHECKING:
    from .backend import ServiceBackend


def credits_fallback(backend: ServiceBackend, *, enabled: bool) -> dict[str, Any]:
    """Store the global setting, return the fresh credits object."""
    setting.set_enabled(value=enabled)
    return route.view(backend.root, backend._clock())  # noqa: SLF001 - the backend's own clock

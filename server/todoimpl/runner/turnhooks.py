"""The hooks every finished turn passes in order; the first that returns True resumes the session at once."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import answered, parsemiss
from .askform import needs_form
from .grant import auto_grant
from .linknudge import needs_link
from .permit import gate

if TYPE_CHECKING:
    from collections.abc import Callable

    from .pipeline import Driver
    from .stream import TurnResult

# parsemiss only files a record and never resumes, so it goes first: every turn reaches it.
HOOKS: tuple[Callable[[Driver, TurnResult, str], bool], ...] = (
    parsemiss.check,
    gate,
    auto_grant,
    needs_form,
    answered.back,
    needs_link,
)

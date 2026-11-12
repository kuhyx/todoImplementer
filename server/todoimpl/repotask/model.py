"""A part: one open section of one of the repo's notes, as the repo task sees it. Pure data, no imports."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Part:
    """One open section (or one whole section-less note) of a repo.

    `key` is the section's own card id `<note id8>-<index>`: the id an older per-section run used, so the
    run dir of such a run still names its part. `manual` = a MANUAL WORK REQUIRED part: it sits on the repo's
    human card (`-1`). `human` = a manual part the run skips; once kuhy answered every ask of it the part is
    released (`manual` and not `human`): still on the human card, but Claude's work (T1994).
    `held` = an older per-section run is still working on it and keeps its own card; `prior` names the
    work an older run that already ended left behind.
    """

    key: str
    note_id: str
    index: int
    title: str
    body: str
    priority: str
    done_check: str | None
    human: bool
    held: bool
    prior: str = ""  # where an older run that ended left its work (reuse it), else empty
    manual: bool = False

    @property
    def actionable(self) -> bool:
        """True when the repo run works on this part (not human work, not held by an older run)."""
        return not (self.human or self.held)

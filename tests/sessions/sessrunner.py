"""A command runner backed by canned results: no test ever opens a terminal."""

from __future__ import annotations

from todoimpl.sessions.commands import CommandResult


class FakeRunner:
    """Return canned results, and record every argv it was asked to run."""

    def __init__(self, responses: dict[tuple[str, ...], CommandResult]) -> None:
        """Store the canned responses keyed by exact argv."""
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], timeout: float = 10.0) -> CommandResult:
        """Return the canned result for ``argv``, or a non-zero miss."""
        del timeout
        self.calls.append(argv)
        if argv in self.responses:
            return self.responses[argv]
        return CommandResult(argv=argv, returncode=1, stdout="", stderr="no fixture")


def ok(argv: tuple[str, ...], stdout: str) -> CommandResult:
    """Build a successful result."""
    return CommandResult(argv=argv, returncode=0, stdout=stdout, stderr="")

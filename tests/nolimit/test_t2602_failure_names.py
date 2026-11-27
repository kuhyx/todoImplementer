"""A red gate's tickets name failing tests, never words of other output (T2602).

2026-11-27, live run on a build-your-x clone below 100 % coverage: pytest-cov's `FAIL Required test coverage
of 100.0% not reached` matched the vitest file pattern, and the ticket read "found Required red". Only a
vitest line naming a test file counts now; the coverage failure stays one ticket for the step.
"""

from __future__ import annotations

import pytest
from todoimpl.nolimit import steps, tickets

COV = "FAIL Required test coverage of 100.0% not reached. Total coverage: 94.12%\n"


def _step(tail: str) -> steps.Step:
    return steps.Step("gate", "pnpm test", 1, tail, 1.0)


@pytest.mark.parametrize(
    ("tail", "want"),
    [
        (COV, []),
        ("ERROR: Coverage failure: total of 94 is less than fail-under=100\n", []),
        (" FAIL  src/lib/dice.test.ts > rolls > six\n", ["src/lib/dice.test.ts"]),
        ("FAIL tests/app.spec.tsx\n", ["tests/app.spec.tsx"]),
        ("FAILED tests/a.py::t1 - assert 1 == 2\n" + COV, ["tests/a.py::t1"]),
    ],
)
def test_t2602_only_test_files_and_ids_are_failures(tail: str, want: list[str]) -> None:
    assert tickets.failures(_step(tail)) == want

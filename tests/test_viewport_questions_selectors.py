"""web/dev/viewport_questions.py must find the answer boxes inside the question drawer only."""

import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "web" / "dev" / "viewport_questions.py"
# Every quoted selector that names a textarea ("textarea[name]", '.ask textarea', "textarea[name=Q1]").
TEXTAREA_SELECTOR = re.compile(r"""(['"])([^'"\n]*\btextarea\b[^'"\n]*)\1""")


def test_t2290_answer_probes_are_scoped_to_the_drawer() -> None:
    """The hidden New task `body` textarea comes first in the DOM; an unscoped probe grabbed it (T2290)."""
    selectors = [m.group(2) for m in TEXTAREA_SELECTOR.finditer(SCRIPT.read_text(encoding="utf-8"))]
    assert selectors, "the script no longer probes a textarea: update this test"
    unscoped = [s for s in selectors if not s.startswith(".drawer ")]
    assert unscoped == []

"""A clipboard stub reads its stdin, like the real xclip and wl-copy (T2474).

The handoff pipes each value into the clipboard (`printf '%s' "$1" | xclip`) under `pipefail`. A stub
that exits without reading lets printf write into a closed pipe: SIGPIPE, exit 141, a gate that fails
only under load.
"""

import re
from pathlib import Path

HERE = Path(__file__).parent
CLIP_STUB = re.compile(r"""stub\(\s*["'](xclip|wl-copy)["']\s*(?:,\s*(?P<body>[^)]*))?\)""")


def test_t2474_every_clipboard_stub_drains_its_stdin() -> None:
    found = [
        (path.name, m.group(0))
        for path in sorted(HERE.glob("test_*.py"))
        for m in CLIP_STUB.finditer(path.read_text())
    ]
    assert found  # the handoff tests stub the clipboard
    assert [stub for stub in found if "cat" not in (stub[1] or "")] == []

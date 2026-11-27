"""T2616: the visibility chore never runs the tool on an entry the tool still answers from its own cache."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from nolimitfakes import kuhy_repo
from todoimpl.nolimit import visibility

if TYPE_CHECKING:
    from pathlib import Path

    from runnerfakes import Env

TOOL_TTL = 86400  # omniroute_offload/_privacy.py CACHE_TTL_S


def _ttl_tool(world: Env, cache: Path, calls: Path) -> None:
    """Install a `free-llm-check-dir` that, like the real one, keeps an entry under a day old untouched."""
    writer = (
        "import json,pathlib,sys,time\n"
        f"pathlib.Path({str(calls)!r}).open('a').write(sys.argv[1]+'\\n')\n"
        f"p=pathlib.Path({str(cache)!r}); c=json.loads(p.read_text())\n"
        "k='kuhyx/'+pathlib.Path(sys.argv[1]).name; e=c.get(k)\n"
        f"if e and time.time()-e['at']<{TOOL_TTL}: sys.exit(0)\n"
        "c[k]={'visibility':'PUBLIC','at':time.time()}; p.write_text(json.dumps(c))\n"
    )
    (world.tmp / "ttl_tool.py").write_text(writer, encoding="utf-8")
    tool = world.bin / visibility.TOOL
    tool.write_text(f'#!/bin/sh\nexec python3 {world.tmp / "ttl_tool.py"} "$@"\n', encoding="utf-8")
    tool.chmod(0o755)


def test_t2616_an_entry_the_tool_still_holds_is_left_alone_and_a_lapsed_one_refreshes(world: Env) -> None:
    cache = world.home / ".cache" / "omniroute_offload" / "visibility.json"
    calls = world.tmp / "calls.txt"
    _ttl_tool(world, cache, calls)
    for name in ("young", "old"):
        kuhy_repo(world, name, test="true")
    now = time.time()
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({
        "kuhyx/young": {"visibility": "PUBLIC", "at": now - 21 * 3600},  # the live C29 window: 20-24 h
        "kuhyx/old": {"visibility": "PRIVATE", "at": now - 25 * 3600},
    }), encoding="utf-8")  # fmt: skip
    report = visibility.run(lambda: True, now)
    assert report == {"refreshed": ["kuhyx/old"], "failed": [], "stale_left": 0}
    assert [line.rsplit("/", 1)[-1] for line in calls.read_text(encoding="utf-8").split()] == ["old"]

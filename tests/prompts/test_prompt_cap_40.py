"""A Bash call and every wait slice end at 40 s: a capped call plus the answer fits in 60 s (T2453)."""

import json

from todoimpl.prompts import standing
from todoimpl.runner import policy


def test_t2453_the_bash_cap_is_40_s_and_the_prompt_says_so() -> None:
    env = json.loads(policy.turn_settings(hooks_off=False))["env"]
    assert env["BASH_DEFAULT_TIMEOUT_MS"] == env["BASH_MAX_TIMEOUT_MS"] == "40000"
    assert "run_job" in standing.WAITS  # a long job is no wait slice any more: it runs outside the session
    assert "50 s" not in standing.GRANT + standing.WAITS

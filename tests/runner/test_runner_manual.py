"""A note titled `MANUAL WORK REQUIRED:` is human work: the scheduler refuses to start Claude on it."""

import pytest
from runnerfakes import Env
from schedfakes import CARD, boot
from todoimpl.runner.scheduler import RunnerError


def test_t1856_start_is_refused_for_manual_work(world: Env) -> None:
    sched, _ = boot(world, title="MANUAL WORK REQUIRED: rotate Claude API key")
    try:
        with pytest.raises(RunnerError, match="MANUAL WORK REQUIRED") as refused:
            sched.start(CARD)
        assert refused.value.code == "disabled"
        assert world.calls() == []
        assert not (world.root / CARD).exists()
    finally:
        sched.close()

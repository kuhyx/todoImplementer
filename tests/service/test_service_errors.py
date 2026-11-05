"""Runner refusals become BackendError with a contract error code (T101)."""

import pytest
from contract_lib import validate
from servicefakes import Rig
from todoimpl.http.backend import ERROR_CODES, BackendError
from todoimpl.runner.scheduler import RunnerError


@pytest.mark.parametrize("code", ["not_found", "conflict", "disabled", "bad_request"])
def test_t101_runner_refusal_keeps_its_code_and_message(rig: Rig, code: str) -> None:
    rig.scheduler.failure = RunnerError("Ship is offered only at Ready to ship", code)
    with pytest.raises(BackendError) as err:
        rig.backend.ship("t1")
    assert (err.value.code, err.value.message) == (code, "Ship is offered only at Ready to ship")
    validate("common", {"code": err.value.code, "message": err.value.message}, "error")


def test_t101_unknown_runner_code_is_internal(rig: Rig) -> None:
    rig.scheduler.failure = RunnerError("odd", "teapot")
    with pytest.raises(BackendError) as err:
        rig.backend.cancel("t1")
    assert err.value.code == "internal"
    assert err.value.code in ERROR_CODES

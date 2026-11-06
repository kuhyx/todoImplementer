# Phone-last regressions

One row per bug, ids global and never reused. The row's test is named `test_t<N>_...`.

| Id | What went wrong | Test |
| --- | --- | --- |
| T1500 | Claude waited for the Pixel or finished without staging it, so phone-only criteria idled for days | tests/runner/test_runner_phone.py |
| T1501 | An `A: phone:` turn parked the run in a generic needs-action state with no staged deploy | tests/runner/test_runner_phone.py |
| T1502 | A turn that staged phone_ready.json but said `D:` ran on to ship before the phone check | tests/runner/test_runner_phone.py |
| T1503 | A phone wait hid a real question from Claude | tests/runner/test_runner_phone.py |
| T1504 | A stale wait stayed after kuhy answered the run | tests/runner/test_runner_phone.py |
| T1505 | A finished phone check re-armed the wait from the stale staged file | tests/runner/test_runner_phone.py |
| T1506 | A phone check that lost the phone did not wait again | tests/runner/test_runner_phone.py |
| T1507 | adb states unauthorized and offline counted as an attached phone | tests/runner/test_runner_phone.py |
| T1508 | A hung or missing adb stalled the watcher or crashed it | tests/runner/test_runner_phone.py |
| T1520 | The live-check prompt never told Claude to test on the emulator and stage the phone install | tests/prompts/test_phone.py |
| T1521 | After plug-in the live check re-ran everything instead of deploying and checking the staged criteria | tests/prompts/test_phone.py |
| T1530 | Phone-only cards sat in the generic needs-action pile | tests/runner/test_runner_phone_flow.py |
| T1531 | Plugging in the Pixel did not start the staged deploy and the phone live check | tests/runner/test_runner_phone_flow.py |
| T1532 | The emulator live-check report was lost when the phone check restarted the stage | tests/runner/test_runner_phone_flow.py |
| T1533 | A restart forgot the phone wait or re-ran the resting turn | tests/runner/test_runner_phone_flow.py |
| T1534 | The watcher forked adb every tick even with no run waiting on the phone | tests/runner/test_runner_phone_flow.py |
| T1535 | Eight waiting cards all hit the one phone at once | tests/runner/test_runner_phone_flow.py |
| T1536 | A cancelled, running or non-waiting run was requeued by the phone watcher | tests/runner/test_runner_phone_flow.py |
| T1540 | The board could not tell a phone wait from any other action Claude asked for | tests/board/test_board_phone.py |
| T1541 | A requeued phone run still showed as needing kuhy | tests/board/test_board_phone.py |
| T1550 | The server never started the phone watcher, so plugging in the Pixel did nothing | tests/service/test_service_phone.py |

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
| T1535 | Only one of several waiting cards was requeued when the Pixel showed, the rest waited for a later tick | tests/runner/test_runner_phone_flow.py |
| T1536 | A cancelled, running or non-waiting run was requeued by the phone watcher | tests/runner/test_runner_phone_flow.py |
| T1540 | The board could not tell a phone wait from any other action Claude asked for | tests/board/test_board_phone.py |
| T1541 | A requeued phone run still showed as needing kuhy | tests/board/test_board_phone.py |
| T1550 | The server never started the phone watcher, so plugging in the Pixel did nothing | tests/service/test_service_phone.py |
| T1818 | A phone-attached turn that still ended `A: phone:` was requeued every 20 s while the Pixel stayed plugged in | tests/runner/test_runner_phone_loop.py |
| T1819 | After such a turn, an unplug and replug never ran the phone check again | tests/runner/test_runner_phone_loop.py |
| T1820 | The board said "Plug in the Pixel" while the phone was in and Claude was asking for something else | tests/runner/test_runner_phone_loop.py |
| T1821 | The attached phone check deployed over kuhy's own app and used the real screen instead of a private slot | tests/prompts/test_phone.py |
| T1822 | A live-check session could ask kuhy to tap, plug, pause music or confirm data use | tests/prompts/test_phone.py |
| T1823 | A feel/audio criterion blocked the card instead of being skipped with a `[~]` row | tests/prompts/test_phone.py |
| T1824 | The staged deploy command lacked `--slot`, so a replug would install over the prod app | tests/prompts/test_phone.py |
| T1825 | The Flutter driver hint pointed at deploying straight onto kuhy's phone | tests/prompts/test_kind.py |
| T1826 | Nothing told a phone hands-on ask apart from any other `A:` ask | tests/runner/test_runner_phone_hands.py |
| T1827 | A live check that asked kuhy to tap rested in Needs you with no runner nudge | tests/runner/test_runner_phone_hands.py |
| T1828 | After the one nudge a repeated ask was nudged again instead of resting with its text | tests/runner/test_runner_phone_hands.py |
| T1829 | The staged `A: phone: plug in` wait for the cable was nudged as a hands-on ask | tests/runner/test_runner_phone_hands.py |
| T1830 | The nudge turn of an attached run lost the attached prompt and fell back to staging | tests/runner/test_runner_phone_hands.py |
| T1831 | A lost-phone `A: phone:` on an attached turn was nudged to do the impossible | tests/runner/test_runner_phone_hands.py |
| T1832 | A note from kuhy did not reset the nudge counter, so the next ask never got its nudge | tests/runner/test_runner_phone_hands.py |
| T1833 | Each board turn is a new claude process, so a card lost its phone test slot between turns | tests/runner/test_runner_claude.py |
| T1834 | A board session could install over, stop or launch kuhy's running workout app: the phone prompts never forbade a non-slot package | tests/prompts/test_phone.py |
| T1981 | kuhy replied to a live check's phone or hands-on ask ("it is ok, push", "no manual checks on my side") and the next live check asked him the same thing again; a live check that takes his reply in and still ends `A:` now drops the phone wait and settles on its checklist (`[~]` rows become the after-ship follow-up) | tests/runner/test_runner_phone_reply.py |

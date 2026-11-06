# Permission regressions

One row per bug, ids global and never reused. The row's test is named `test_t<N>_...`. Ids T1600-T1699.

| Id | What went wrong | Test |
| --- | --- | --- |
| T1600 | A turn stopped on a denied Bash call and nothing learned a rule for it | tests/runner/test_runner_permissions.py |
| T1601 | Edit, Write, Read, MCP and WebFetch denials had no narrow rule | tests/runner/test_runner_permissions.py |
| T1602 | sudo, system systemctl, curl-to-shell, rm -r outside and settings edits could have been auto-allowed | tests/runner/test_runner_permissions.py |
| T1603 | The never-list also blocked safe look-alikes (user systemctl, rm inside the worktree, /tmp) | tests/runner/test_runner_permissions.py |
| T1604 | Outside paths, secrets, risky MCP tools and hook blocks were learned as rules | tests/runner/test_runner_permissions.py |
| T1605 | A session policy file did not lift the auto-allow never-list | tests/runner/test_runner_permissions.py |
| T1606 | A sensitive-file refusal in the worktree got a useless rule instead of the write-via-Bash advice | tests/runner/test_runner_permissions.py |
| T1607 | The fix command needed a directory or was not one line | tests/runner/test_runner_permissions.py |
| T1608 | The learned allow list lost scopes or broke on a corrupt allow.json | tests/runner/test_runner_permissions.py |
| T1609 | The stream parser dropped permission denials, hook errors and which denial ended the turn | tests/runner/test_runner_permissions.py |
| T1610 | A nice or timeout wrapper ended up in the rule, or an unbalanced quote crashed the splitter | tests/runner/test_runner_permissions.py |
| T1620 | A permission stop sent the card to Needs you instead of learning the rule and rerunning | tests/runner/test_runner_permit_flow.py |
| T1621 | A rule that never worked reran forever instead of capping at two and giving kuhy a command | tests/runner/test_runner_permit_flow.py |
| T1622 | A sudo denial was auto-allowed or had no terminal command on the card | tests/runner/test_runner_permit_flow.py |
| T1623 | Done, rerun did not continue the failed stage | tests/runner/test_runner_permit_flow.py |
| T1624 | Go reran after a failing command or ran a card without a command | tests/runner/test_runner_permit_flow.py |
| T1625 | A hook block was offered a command or a rule although a hook cannot be lifted | tests/runner/test_runner_permit_flow.py |
| T1626 | A sensitive file in the worktree sent the card to Needs you instead of rerunning with the Bash advice | tests/runner/test_runner_permit_flow.py |
| T1627 | A question stop with an old denial was treated as a permission stop | tests/runner/test_runner_permit_flow.py |
| T1628 | A refused git push was treated as a permission gap | tests/runner/test_runner_permit_flow.py |
| T1640 | Without a policy file the session argv changed | tests/runner/test_runner_policy.py |
| T1641 | The policy file did not set mode, dirs, hooks and deny | tests/runner/test_runner_policy.py |
| T1642 | A null deny dropped the built-in deny list or the read-only role lost its deny | tests/runner/test_runner_policy.py |
| T1643 | An invalid policy file loosened or broke a run instead of warning | tests/runner/test_runner_policy.py |
| T1644 | An unreadable policy file crashed the turn | tests/runner/test_runner_policy.py |
| T1645 | The policy path skipped the never-list switch or the sensitive-file advice | tests/runner/test_runner_policy.py |
| T1646 | A policy warning never reached the feed | tests/runner/test_runner_policy.py |
| T1660 | The permission card hid its command or broke the contract | tests/service/test_service_permission.py |
| T1661 | Go did not run the command and rerun through the scheduler | tests/service/test_service_permission.py |
| T1662 | A failing Go command lost its output or reran anyway | tests/service/test_service_permission.py |
| T1663 | Done, rerun did not rerun | tests/service/test_service_permission.py |
| T1664 | A card without a command accepted Go | tests/service/test_service_permission.py |
| T1680 | The drawer hid a permission block's command | web/src/components/sections.test.ts |
| T1681 | Copy and Go on a permission card did not copy the command or post to /go | web/src/components/drawer-actions.test.ts |
| T1665 | The command runner lost output or the exit code | tests/service/test_service_permission.py |
| T1666 | A Go command that hangs was never killed | tests/service/test_service_permission.py |

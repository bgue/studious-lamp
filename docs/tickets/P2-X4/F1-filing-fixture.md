# P2-X4-F1: filing-check fixture names a core command

Goal: three tests in `packages/tl-core/tests/test_agent_filing_check.py` pass again on p2/x4.

Root cause (found): the `module_command` fixture declares `command_words={"CreateRecord": ...}`.
`CreateRecord` is a core command. X4-S4/S6 refuse a module that names a core command whole
(`command_index` skips it; `module_commands(reserved=...)` refuses it). So the fake module is
skipped, `CreateRecord` is treated as core, and a `viewer` grant (any module role) files. The
code is right (a module may never gate a core command); the fixture is stale. No code change.

Fix: the fixture declares its own module command (`VaultCreate`, a subclass defined in the test
module, so not a core name) with a proposable tool; `cmd()`/`TOOL` follow the active fixture.
No assertion changed.

Allowed paths: `packages/tl-core/tests/test_agent_filing_check.py`, this file, the report.
Acceptance: the gate command of the brief passes; ruff, format, scoped pyright clean.

# V3-P2 · `just gate-changed` and `dev/commit-check.sh`
kind: ticket · review: full · branch `p2/v3-p2-tools` · worktree `/home/user/wt/v3p/p2` · base `p2/v3-forms`
Process: `docs/build-spec/process-v3.md` rules 7 and 8.

## Goal
1. `dev/gate-changed.sh [<base>]` and `just gate-changed [base]` (default base: `git merge-base HEAD p2/v3-forms`,
   else `origin/claude/wizardly-allen-m2v96s`). Steps, stopping at the first red, each printing one line:
   - `ruff check` and `ruff format --check` on changed `.py` files; `pyright` on changed `.py` files only;
   - `dev/commit-check.sh <base>`;
   - `bash dev/gate.sh <paths>` where paths = the `tests` dir of every package with a changed file
     (`packages/<p>/tests`, `packages/tl-modules/<m>/tests`), plus `tests/<x>` dirs whose files changed, plus the
     confidentiality walk set: the tests that use `tests/confidentiality/twin_channels.py`, every
     `tests/confidentiality/test_*walk*.py`, `test_hidden_sql_equal_old.py`, `test_paths_equal_old.py`;
   - `bash dev/gate.sh --postgres tests/confidentiality` only when the diff touches `packages/tl-adapters/`,
     `packages/tl-core/src/tl_core/confidentiality.py` or any `projectors/` path;
   - `bash dev/gate.sh tests/perf` when `tests/perf` exists.
   Heavy steps take `flock /tmp/claude-0/tl-gate.lock` so two worktrees never run a heavy step at once.
   Last line `gate: PASS` or `gate: FAIL`. Same output conventions as `dev/gate.sh`. `--dry-run` prints the plan
   (the steps and paths) and runs nothing.
2. `dev/commit-check.sh <base>`: for each commit in `<base>..HEAD`, fail on a model name (Claude, Opus, Sonnet,
   Haiku, Fable, GPT; case-insensitive, whole word) in the subject or body outside the two trailer lines
   (`Co-Authored-By:` and `Claude-Session:`), and in any added line of `docs/reports/**`. Print one line per hit
   `<sha7> <where> <word>`. Exit 1 on a hit, 0 when clean.

## Tests
`dev/tests/test_gate_changed.py` and `dev/tests/test_commit_check.py`: fixture git repo in `tmp_path`; pin the
`--dry-run` plan for three diffs (a module file, a core confidentiality file, a docs-only change); pin
commit-check output for a clean commit, a body hit, a trailer-only mention (clean) and a report-line hit.

## Gate
`just check`; `just gate dev/tests`. Report `docs/reports/P2-FORMS/V3-P2.md`, at most 15 lines. Subject `V3-P2:`.

# P2-PUNCH-S4 — SR3 fix: a punch item is raised only from a record that names no subject

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: security, confidentiality, quality
Branch: `p2/punch-s4-source-rule`
Worktree: `/home/user/wt/punch/s4` (from `p2/punch` head d9000696)

## Goal
SR3 (2026-11-13) found two leaks of a hidden record's key through a visible punch item:
- **F1 HI.** `tl_core/confidentiality.py:_subject_chain` joins the constraint step (`k`) only for the record under
  test, never at a later hop. Punch -> constraint -> restricted correspondence: the punch item stays visible and
  shows the hidden constraint's key (`source_key`), `from=<key>` is an existence test, and `PunchItem.Raised` names
  the hidden id on events, stream and webhooks.
- **F2 MD.** `_HOPS` = 2 and `handle_raise_punch_item` (`handlers/punch.py:133`) accepts any visible record, so
  punch -> punch -> punch -> hidden (or punch -> work order -> requisition -> hidden) is a 3-hop chain past the join.

Decision (orchestrator, 2026-11-13): no core change. Bound every chain at the punch end. A punch item may only be
raised from a record that **names no subject itself**: not `core.Constraint`, and not any type listed in
`tl_core.confidentiality.SUBJECT_LINKS` (derive the set from that tuple, do not hard-code the five requisition
types and the punch type, so a later linked module is refused too). Today's longest chain then stays within two
hops: constraint (k) -> punch -> record; work order -> requisition -> IWP/CWP (requisitions only serve IWP or CWP).

## Steps
1. `packages/tl-modules/quality/src/tl_mod_quality/handlers/punch.py` `handle_raise_punch_item`: after
   `load_record` (which already answers a hidden record exactly as a missing one, so keep that order), refuse with
   `PunchRuleError(MSG_SOURCE_LINKED)` when the record's type is `core.Constraint` or a `SUBJECT_LINKS` type.
   `MSG_SOURCE_LINKED = "a punch item is raised from the work itself, not from a constraint, requisition, work order
   or another punch item"` (fixed text; it names only the type class of a record the actor can already see).
   Edits never change the source (check `handle_edit_punch_item`; if an edit can change `source_id`, apply the same
   rule there).
2. Tests in `packages/tl-modules/quality/tests/test_punch_visibility.py` (or `test_punch_commands.py`):
   - SR3's two proofs turned into regressions (scratch file
     `/tmp/claude-0/-home-user-studious-lamp/c1e9f617-74c2-581f-aa0c-d2601bd9e1da/scratchpad/sr3/test_sr3.py`; read
     it, port the setup, do not import it): raising from a constraint on the hidden record is refused with the
     rule message; raising P2 from a visible punch item P1 is refused.
   - Raising from a work order and from a requisition is refused (one parametrised test, if the requisitions
     fixtures are cheap to reach from `punch_world`; else one of them and a unit test of the type set).
   - A hidden source still answers exactly as a missing one (the existing check stays green; do not weaken it).
   - The type set equals `{"core.Constraint"} | {row[0] for row in SUBJECT_LINKS}` (pins the derivation).
3. MCP `propose_punch_item` (`tl_mcp` punch tool) resolves `from_key`: if it can refuse a linked source early with
   the same text, do it; if not, the accept path refuses through the handler (say which in the report).
4. Docs: `docs/tickets/P2-PUNCH/README.md` "Risks" line on `_HOPS` and the quality module README "Record shape" or
   rules section: one sentence each stating the source rule and why (chain bound).
5. If any existing test or demo raises a punch item from a linked record, change its source to a plain record and
   say so in the report; do not change the rule.

## Allowed paths
`packages/tl-modules/quality/**`, `packages/tl-mcp/src/tl_mcp/**punch*`, `packages/tl-mcp/tests/**punch*`,
`docs/tickets/P2-PUNCH/README.md`, `docs/reports/P2-PUNCH/S4.md`, `dev/demos/P2-PUNCH*` (only if step 5 needs it).
Not `packages/tl-core/**` (no core change; if you find you need one, stop and write under Blocked).

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run pytest -q -p no:cacheprovider --basetemp=/tmp/pt-punch-s4 packages/tl-modules/quality/tests packages/tl-mcp/tests -k "punch or quality"
```
One pytest session at a time. Do NOT run `just gate` or the whole suite. Mutation: one sentinel plus at most 3
targeted mutants on the new guard (drop the check; check only `core.Constraint`; check only the punch type), each
must be killed; report in 3 lines.

## Report requirements
Builder return <= 15 lines; report `docs/reports/P2-PUNCH/S4.md` <= 60 lines. Commit subjects `P2-PUNCH-S4: ...`;
body ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
`Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(builder writes here)

## Decision
(orchestrator writes here)

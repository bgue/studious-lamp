# P2-I1-S6 — Expected link of a released CWP in the default registry

Status: ready
Tier: builder
Kind: piece
Review: full
Labels: schema
Depends on: S4 (merged)
Approver (schema): orchestrator under P2-Q10; line in `docs/reports/APPROVALS.md` at merge
Branch: `p2/i1-s6-expected-link`
Worktree: `/home/user/wt/i1-s6` (from `p2/i1` head)

## Goal
`tl links expected` and the unmet-expectation reads report a CWP at `Released for IWP development` that has no active
`requires` link to an `awp.EWPRef`. Today they report nothing: `default_expected_links()` reads only
`schema/fixtures/links/`, while the expectation lives in `schema/modules/awp/cwp.yaml` (decision Q1, answered yes by the
orchestrator). Release is never refused for the miss (S4 checked); this is the visible gap only.

## Brief references (pasted)
- `packages/tl-core/src/tl_core/links/expected.py:91` `parse_expected_links`: the record type of a class is
  `<tl:module>.<ClassName>`; only the class annotation `tl:expects_link` is read; a schema with no `tl:module` raises.
- Model file: `schema/fixtures/links/core-record.yaml` (comment header, `id`, `name`, `prefixes`, `imports`, `default_range`,
  `annotations: {tl:module: core}`, `classes: Record: annotations: tl:expects_link: [...]`).
- The entry to copy exactly from `schema/modules/awp/cwp.yaml:33-38`: relation `requires`, direction `out`, target_type
  `awp.EWPRef`, by_state `Released for IWP development`, label `engineering work package`.

## Context (read these, nothing else)
`schema/fixtures/links/core-record.yaml`; `schema/modules/awp/cwp.yaml` lines 1-40; `expected.py` lines 91-190;
`dev/accept/P2-I1/S4.py` (the line that builds a registry from `cwp.yaml`, to reuse its seed); `schema/annotations` is
`schema/core/annotations.yaml` (`tl:expects_link`). may explore: the tests that import `default_expected_links`.

## Allowed paths
- `schema/fixtures/links/awp.yaml` (create) — one class `CWP`, `tl:module: awp`, the single entry above, no other class.
- `dev/accept/P2-I1/S6.py` (create), `docs/reports/P2-I1/S6.md` (create)
- `just gen` output only if the generator reads this file (it should not; if it does, commit the output).
Not allowed: `schema/modules/awp/**` (the module copy stays; one source of truth is a follow-up, say so in the report),
`tl_core`, any test file (T11 adds `tl links expected` to the seed test), generated files by hand.

## Acceptance (run once; no pytest)
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I1/S6.py
just gate <the test directories that import default_expected_links or run `tl links expected`; find with grep, at most 3>
```
`S6.py` (SQLite tmp db; one `PASS <check>` per check; final `S6 ok`; <= 40 lines): `default_expected_links()` lists
`awp.CWP` with exactly one expectation equal to the one in `cwp.yaml` (compare the parsed fields); a seeded CWP in
`In development` has no miss; a seeded CWP at `Released for IWP development` with no `requires` link to an EWPRef has one
`MissingLink` (use the S4 seed helpers; read how `S4.py` releases a CWP); after a `requires` link to an `awp.EWPRef` record
(S4.py records one) the miss is gone; `Release` still succeeds with the miss (never refused);
`uv run tl links expected --db <tmp db>` prints the miss (copy the way W0 scripts call `tl`, or call the CLI runner).

## Guards T11 will mutate
By-state spelling; `target_type` (an EWPRef link counts, a PWPRef link does not); direction `out`.

## Approval line (orchestrator at merge)
`docs/reports/APPROVALS.md`: `schema/fixtures/links/awp.yaml` expected link `awp.CWP requires awp.EWPRef at Released`.

## Report requirements
`docs/templates/haiku-report.md` shape, <= 60 lines: deviations first; files; acceptance output (<= 5 lines per
command); candidate learnings. Subject `P2-I1-S6: ...`; no model names; commit trailer = the harness attribution line, then
`Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. Builder return <= 15 lines.

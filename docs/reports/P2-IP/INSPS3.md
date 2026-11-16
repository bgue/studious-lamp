# P2-IP-INSPS3: readiness check `inspections_planned` for real

Deviations: report path is `docs/reports/P2-IP/INSPS3.md` (dispatch), not `P2-INSP/S3.md`; branch `p2/insp-s3-readiness` as dispatched.
`packages/tl-modules/awp/README.md` line 199 still lists the placeholder (outside Allowed paths; left, see Questions).

## Done
- `tl_mod_quality/checks.py`: `evaluate(conn, iwp, today)`, rows of design section 5; one SELECT over
  `cur_quality_inspection` joined to `cur_core_record` by `for_iwp_id`; setting read with
  `value_of(conn, key, project=project_of_scope(scope))` (as awp `setting_value`); `watches`
  `{quality.Inspection}`; detail is counts only; a failed read or more than 1000 rows is `unknown`.
- Entry point added to quality `pyproject.toml`; line removed from awp `pyproject.toml`; placeholder
  removed from `checks_na.py` (docstring: four).
- Decisions: Done or Verified count as done; a Cancelled reinspection does not satisfy a rejected hold
  point; `conditional` hold points do not block (spec names `reject` only).
- Pins: `dev/accept/P2-I2/T06b.py` (row removed, comment, labels "four"); `test_readiness_registry.py` unchanged (passes).

## Tests (`quality/tests/test_readiness.py`, 12)
Spec items 1 to 5 plus: start on the scheduled day is not late, conditional hold does not block,
rejected witness does not block, failed read is unknown.

## Acceptance
- ruff format --check / ruff check: clean. pyright (two files): 0 errors.
- `just gate ...`: part 1: exit 0, 34 passed; `gate: PASS`.
- `uv run python dev/accept/P2-I2/T06b.py`: exit 0.

## Mutation
Sentinel (required flag inverted) killed. 5 targeted: `<`->`<=` on start (survived, +test day-boundary,
now killed), reinspection child ignored (killed), `reject`->`!= accept` (survived, +conditional hold test,
now killed), point=hold ignored (killed), cancelled not excluded (killed). 5/5 killed after +2 tests.

## Candidate learnings
SQLite `IS NOT 'x'` is not Postgres; the check's SQL uses `IS NULL OR <>`. Postgres run not done (SQLite gate).

## Questions
Update awp README line 199 (and `p2_w0` demos listing five names) in a follow-up?

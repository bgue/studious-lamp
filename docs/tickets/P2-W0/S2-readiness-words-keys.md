# P2-W0-W0-B1 — Readiness contract, reserved prefixes, settings keys, access words

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: core, schema, settings
Depends on: —
Branch: `p2/w0-b1`
Approver (settings, access words): the orchestrator under P2-Q10 (line in `docs/memory/APPROVALS.md` at merge)

## Goal
After this piece the shared Phase 2 foundations exist on the trunk: the frozen readiness contract with its registry
and contract harness; the reserved correlation and source prefixes of Phase 2; the 11 Phase 2 settings keys at their
defaults; and the access-word table (`schema/settings/access-words.yaml`) with its loader, so wave 1 modules name fine
words and wave-0 roles can read them. No module uses any of it yet.

## Brief references (pasted, abridged; the files below are authoritative)
> `specs/wave0.md` §2: fine words as data: `{version: 1, words: {awp.view: read, awp.cwp.edit: user, awp.cwp.release:
> controller, ...}}`, one row for **every word** of `specs/m3-wbs-cwp.md` §3 and `specs/m4-materials.md` §3 (the Access
> word column; the default-role column gives the table word: viewer -> `read`, user -> `user`, superuser -> `controller`;
> "company superuser, else admin" -> `controller`). `tl_core.auth.access_words.load_access_words()` and
> `table_word(word)`; an unknown table word (outside `read`, `user`, `controller`) or a duplicate word is an
> `AccessWordError` at start-up (fail closed). `table_word(w)` returns `w` itself when `w` is already a table word.
> `specs/wave0.md` §3: `types.py` is `docs/build-spec/phase2-contracts-draft.md` §1 **verbatim** (the first code block
> of §1, docstring and all; frozen). `registry.load_checks() -> dict[str, ReadinessCheck]` (entry-point group
> `throughline.readiness_checks`; a plugin that fails to load raises `ReadinessLoadError` at first use; two checks with
> one name raise). Harness `tl_core/readiness/harness.py::check_readiness_contract(check, world)` (plan check F6).
> Reserved: correlation prefixes `ready:`, `rollup:`, `progress:`; source prefix `job:` (contracts draft §7).
> Settings (`schema/settings/platform.yaml`, one gated change): `awp.iwp.ready_lead_weeks` (4), `awp.backlog.target_weeks`
> (4), `awp.iwp.size_hours` ([60, 850]), `awp.release.signoff_roles` (`[superuser]`, roles of the role table),
> `awp.release.allow_unknown_checks` (false), `awp.rules_of_credit.set` (empty), `awp.constraint.aging_days` (14),
> `awp.constraint.auto_raise` (true), `awp.constraint.default_owners` ([]), `materials.receipt.mtr_required_categories`
> ([]; a project lists `ItemCategory` codes), `scaffold.inspection.interval_days` (7); scopes and `lockable` per brief
> §30.1 (read it for the rules; defaults the brief does not give are proposed); follow the shape of the existing keys.
> R-P2-3 is closed by P1-SEC1: do not change `request_model` / `refuse_role_claim`.

## Interfaces
```python
# tl_core/readiness/harness.py  (no pytest import; raises ContractViolation(AssertionError) naming the broken rule)
@dataclass(frozen=True)
class ContractWorld:
    open_readonly: Callable[[], Connection]   # a connection on which any write must fail or be detected
    iwp: IwpFacts                              # an IWP the check can answer
    today: date
    record_types: frozenset[str]               # existing record types, for `watches`
    expect_n_a: bool = False                   # True: the check must answer `n_a` with a non-empty detail for this world
def check_readiness_contract(check: ReadinessCheck, world: ContractWorld) -> None: ...
# rules: result is a CheckResult whose name == check.name (snake case, <= MAX_NAME_CHARS) and version == check.version;
# no write statement executed (listen on the connection's cursor-execute and fail on INSERT/UPDATE/DELETE/DDL);
# len(resolve_via) <= MAX_RESOLVE_VIA, len(detail) <= MAX_DETAIL_CHARS, detail has no path separator and no "Traceback";
# watches is a non-empty frozenset subset of world.record_types; expect_n_a -> state == "n_a".
# tl_core/readiness/registry.py:  class ReadinessLoadError(Exception);  def load_checks(entry_points=None) -> dict[str, ReadinessCheck]
#   (the optional argument is an iterable of entry points, so a test can inject plugins; default: importlib.metadata group)
# tl_core/readiness/__init__.py: re-export the public names of types, registry, harness.
# tl_core/auth/access_words.py:
class AccessWordError(Exception): ...
def load_access_words(path: Path | None = None) -> Mapping[str, str]   # word -> table word; default schema/settings/access-words.yaml via the repo's schema-file locator
def table_word(word: str) -> str                                         # fine -> table word; a table word returns itself; unknown -> AccessWordError
TABLE_WORDS = ("read", "user", "controller")
```
`reserved.py`: `RESERVED_CORRELATION_PREFIXES` gains `ready:`, `rollup:`, `progress:`; `RESERVED_SOURCE_PREFIXES` gains `job:`.
Before adding `job:` grep the repo for events or tests that already use a source starting `job:` (report the result; if
any real producer uses it, stop and report *Blocked*).

## Context (<= 10 files)
- `docs/build-spec/phase2-contracts-draft.md` §1 and §7; `docs/build-spec/specs/m3-wbs-cwp.md` §3; `docs/build-spec/specs/m4-materials.md` §3
- `packages/tl-core/src/tl_core/services/reserved.py`; `packages/tl-core/src/tl_core/settings/{registry.py,types.py}`; `schema/settings/platform.yaml`
- `docs/brief-v0.4.md` §30.1 (settings rules)
- `packages/tl-core/tests/test_settings_definitions.py` (pinned lists you must update)
may explore: `packages/tl-core/src/tl_core/integration/contract.py` (existing prefixes), `packages/tl-core/src/tl_core/derivation/` (entry-point loading style), `tests/auth/authworld.py`

## Allowed paths
- `packages/tl-core/src/tl_core/readiness/{__init__,types,registry,harness}.py` (create)
- `packages/tl-core/src/tl_core/services/reserved.py`
- `packages/tl-core/src/tl_core/auth/access_words.py` (create)
- `schema/settings/platform.yaml`, `schema/settings/access-words.yaml` (create); `packages/tl-schema/src/tl_schema/generated/**` only by `just gen` if the settings keys are generated
- `tests/contract/test_readiness_contract.py` (create; calls the harness on one inline `n_a` sample check and on three broken samples that must raise: a writing check, an over-long detail, an unknown `watches` type; **written, not run**)
- pinned settings lists in existing tests (consequential pins, listed in the report), e.g. `packages/tl-core/tests/test_settings_definitions.py`
- `dev/accept/P2-W0/W0-B1.py` (create), `docs/reports/P2-W0/W0-B1.md` (create)

## Acceptance (run these, once; no pytest)
```
just gen            # only if the settings are generated
just check
uv run python -c "from tl_core.readiness.registry import load_checks; print(load_checks())"     # {}
uv run python dev/accept/P2-W0/W0-B1.py
```
`dev/accept/P2-W0/W0-B1.py` (SQLite, exit 0, one `PASS <check>` per check) proves: `load_checks()` is `{}`; injected
plugins: two with one name raise, one that fails to load raises `ReadinessLoadError`; the harness passes a sample `n_a`
check and raises `ContractViolation` for each of the three broken samples; `refuse_reserved_fields` refuses
`correlation_id="rollup:x"`, `"ready:x"`, `"progress:x"` and `source="job:x"`, and a body through the API (the existing
test-client pattern of `packages/tl-api/tests/`) with `correlation_id: rollup:x` is 422; the 11 keys read at their defaults
through the settings resolver; `load_access_words()` contains every word found by scanning the two specs' §3 for
`awp.*`/`materials.*` words, each mapped to a table word as stated above; a copy with an unknown table word and a copy with
a duplicate word each raise `AccessWordError`; `table_word("user") == "user"`.

## Tests to add
Only `tests/contract/test_readiness_contract.py` (above). TB writes `tests/contract/test_reserved_prefixes.py` and
`tests/settings/test_phase2_keys.py`; TA writes `packages/tl-core/tests/auth/test_access_words.py`.

## Mutation guards (run by TB/TA)
Duplicate word and duplicate check name raise; unknown table word fails closed; a prefix removed from the reserved tuple
lets `rollup:x` through; harness write-detection removed lets the writing sample pass.

## Report requirements
Standard piece report (<= 60 lines): deviations first; the `job:` grep result; pinned-list changes; how each setting's
scope and `lockable` were decided (one line each, proposed defaults marked).

## Escalation triggers
- Stop and report *Blocked* if: `types.py` cannot be copied verbatim (type-checker conflict: report, do not edit); a
  settings key needs a new settings feature; an existing producer uses a `job:` source or any of the new correlation prefixes.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)

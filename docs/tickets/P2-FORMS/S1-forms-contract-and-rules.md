# P2-FORMS S1 — Forms engine in core: the frozen contract and the pure rules

kind: piece
review: full
branch: p2/forms-s1-contract
worktree: /home/user/wt/forms/s1
Depends on: `p2/ip` at INSP C1 (INSP-S1 merged: the question shape is documented in
`schema/modules/quality/checklist.yaml`). Independent of S2 (no shared file). Gated: core interface (ADR-0031
decisions 1, 3, 5; APPROVALS line before merge). Labels: core. No schema, no settings, no words.

## Why
ADR-0031: the engine is a contract plus pure functions in `tl_core/forms/`; it reads no table and writes no event. Every
forms item (schema S2, commands S3, form sources S3s, projections, runner, CLI, routes, tools, intake) is written
against the names frozen here. `quality.insp_rules` (INSP T00, staged, not merged when this is written) holds the
format 1 rules inside the quality module; this piece writes the generic rules in core. The two copies are joined by a
later ticket (T13: `insp_rules` re-exports the core pair), never by this piece, so S1 does not wait for T00.
Format 1 behaviour (problem texts, bounds) must match T00's provided test for the two validate functions.

## Goal (create exactly these names)
1. `packages/tl-core/src/tl_core/forms/__init__.py` (empty docstring), `types.py`, `rules.py`, `registry.py`.
2. `types.py`, frozen once merged (module docstring says so, in the style of `tl_core/qr/types.py`; imports no web,
   CLI, MCP, TUI or module code):
   ```python
   FORM_SOURCE_ENTRY_POINT = "throughline.form_sources"; MAX_SOURCES = 32
   FORMAT_1, FORMAT_2 = 1, 2
   MAX_FIELDS = 60; MAX_FIELD_TEXT = 200; MAX_CHOICES = 8; MAX_SECTION = 64; MAX_HELP = 300
   MAX_ANSWER_TEXT = 1000; MAX_NOTE = 300; MAX_PHOTOS = 10; MAX_CONDITION_DEPTH = 3
   INTAKE_MAX_FIELDS = 8; INTAKE_TEXT_MAX = 280; INTAKE_MAX_ACCEPTS = 5
   KINDS_1 = ("yes_no_na", "number", "text", "choice"); KINDS_2 = KINDS_1 + ("multi", "date", "photo")
   KEYS_1 = ("id","text","kind","required","unit","min","max","choices","fails_when"); KEYS_2 = KEYS_1 + ("section","help","visible_when")
   RESERVED_CLAIM_IDS = ("claim_name", "claim_company", "claim_phone")
   INTAKE_PURPOSES = ("request", "sign_on")
   class TemplateRef(BaseModel):   # extra="forbid", frozen
       source_type: str            # record type that stores the template ("forms.Template", "quality.Checklist", ...)
       source_id: str; version: int  # >= 1
       fmt: Literal[1, 2]; content_hash: str   # 64 lower hex
   class FormBinding(BaseModel):   # extra="forbid"
       record_type: str; key: str; template: TemplateRef | None
       available: bool; reason: str | None       # reason: a fixed word; set only when available is false
       command: str | None; fixed_args: dict[str, Any]; answers_arg: str | None
       expected_version: int | None; prefill: list[dict[str, Any]]   # answers {q, value, note}, at most MAX_FIELDS
   @runtime_checkable
   class FormSource(Protocol):
       record_type: str; view_word: str
       def binding(self, conn: Connection, record_id: str, viewer: Viewer, now: datetime) -> FormBinding | None: ...
   ```
   `FormBinding` refuses `available=True` without template, command and `answers_arg`; refuses `reason` with
   `available=True`; refuses a `fixed_args` key equal to `answers_arg`; refuses a `fixed_args` or `prefill` that does not
   serialise to JSON within 4 KB / 64 KB. `FormSource.binding` docstring rules: a pure read; never writes; `None` for a
   record the viewer cannot see, for an unknown record, and for a record type with no form; never raises for a bad
   or hidden record; never opens the network; `available=False` only for a record the viewer can already read.
3. `registry.py`: `load_form_sources() -> dict[str, FormSource]` keyed by record type; loads the entry-point group;
   a plugin that fails to load is an error at first use; two sources for one record type is an error; more than
   `MAX_SOURCES` is an error; a plugin that does not satisfy the protocol is an error. Follow `tl_core/qr/registry.py`.
4. `rules.py`, pure over plain dicts (the JSON a record stores). No database, clock or `tl_core` import except
   `types`. Never mutate inputs. Signatures:
   ```python
   def validate_questions(fields: list[dict], *, fmt: int = 1) -> list[str]     # problems; [] = publishable
   def validate_answers(fields: list[dict], answers: list[dict], *, fmt: int = 1,
                        partial: bool = False, intake: bool = False) -> list[str]
   def visible_ids(fields: list[dict], answers: list[dict]) -> list[str]        # in field order
   def content_hash(fields: list[dict], *, fmt: int) -> str                     # SHA-256 hex
   def intake_problems(fields: list[dict], *, purpose: str, accepts_as: list[str]) -> list[str]
   ```
   `fmt` other than 1 or 2 raises `ValueError`. Rules:
   - **Format 1** is the INSP-S1 question `{id, text, kind, required, unit, min, max, choices, fails_when}` and its
     rules exactly as `docs/tickets/P2-INSP/T00-insp-rules.md` states them for `validate_questions` and
     `validate_answers` (problem texts start `q<n>:`, or `question <i>:` for an id that is not `q` plus digits; the
     fixed phrase `q1: answer required`; bool is not a number; an out-of-range number is a valid answer). Unknown or
     missing key, kind outside `KINDS_1`: problems.
   - **Format 2** relaxes only: keys `KEYS_2` (the three new keys optional, absent or null); kinds `KINDS_2`; ids
     match `^[a-z][a-z0-9_]{0,31}$` (a superset of `q<digits>`: the intake claim ids need it, decision D2 of STATE.md).
     `section` ≤ 64, `help` ≤ 300 (strings or null); `multi` needs 1 to 8 distinct choices; `fails_when` only on
     `yes_no_na` and `number` as in format 1, null on every other kind (including the new ones).
   - **`visible_when`** (format 2 only): a node is exactly one of `{q, is}`, `{q, in: [..1 to 8 values..]}`,
     `{q, gte: number}`, `{q, lte: number}`, `{q, answered: bool}`, `{all: [..1 to 8 nodes..]}`,
     `{any: [..]}`, `{not: node}`. Combinator depth at most `MAX_CONDITION_DEPTH` (leaf = 0, so `not(all(any(leaf)))`
     is 3, four is refused). A leaf names an earlier field only (not itself, not a later or unknown one). Any
     other key, two operators in a node, or a non-dict node is a problem. Problems start with the field's label.
   - **`visible_ids`**: fields shown for these answers, in field order. A field with no `visible_when` is shown. A
     hidden field counts as unanswered for every later condition even when the answers list holds a value for it
     (so a stray answer cannot open a chain). `is` compares equality (a bool is not equal to a number), `in`
     membership, `gte`/`lte` inclusive on int or float (a non-number answer is false), `answered` true or false.
   - **`validate_answers`**: shape per field kind as format 1; `multi` a list of distinct members of `choices`
     (empty allowed); `date` a `YYYY-MM-DD` string that is a real date; `photo` a list of 1 to `MAX_PHOTOS` distinct
     26-character ULID strings (use the Crockford pattern of the schema `Ulid` range). An answer to an unknown or
     hidden field is a problem naming that field; a hidden required field is not required; a visible required field
     with no answer is the phrase `<id>: answer required`. `partial=True` (drafts) skips only the required check.
     `intake=True` caps a `text` answer at `INTAKE_TEXT_MAX`. Format 1 callers pass nothing and get the T00 behaviour.
     (`validate_answers` takes the format only to pick the key and kind set; visibility applies to every field.)
   - **`content_hash`**: SHA-256 hex of the canonical JSON of `{"format": fmt, "fields": fields}`: `sort_keys`,
     separators `(",", ":")`, `ensure_ascii=False`, UTF-8; independent of dict key order, dependent on field order.
   - **`intake_problems`** (ADR-0032 decision 2; checks the fields of a template that is to be `intake: public`, on top
     of a clean `validate_questions(fields, fmt=2)`): at most `INTAKE_MAX_FIELDS`; kinds `text`, `choice`, `number`
     only; no `visible_when`; a `number` has both `min` and `max`; a field whose id is in `RESERVED_CLAIM_IDS` is
     kind `text`; `purpose` in `INTAKE_PURPOSES`; `accepts_as` 1 to `INTAKE_MAX_ACCEPTS` distinct names matching
     `^[A-Z][A-Za-z0-9]{2,63}$`. Whether those commands exist is not checked here (S7).
5. `failed_questions` and `result_of` are NOT lifted: they carry meaning and stay in `tl_mod_quality.insp_rules`.

## Allowed paths
- `packages/tl-core/src/tl_core/forms/{__init__,types,rules,registry}.py` (create)
- `packages/tl-core/tests/test_forms_rules.py` (create: byte-identical copy of
  `docs/tickets/P2-FORMS/provided/S1_test_forms_rules.py`, phrase 101)
- `packages/tl-core/tests/test_forms_rules_format1.py` (create; see Tests to add)
- `packages/tl-core/tests/test_forms_contract.py` (create)
- `docs/reports/P2-FORMS/S1.md` (create)
Not allowed: any other `tl_core` file (`modules.py` belongs to P2-X4; `confidentiality.py` to CONF-ROWS), any module
package, `schema/**`, settings, words, `tl_api`, `tl_cli`, `tl_mcp`, `tl_tui`, `tl_web`, `pyproject.toml`.

## Tests to add
- The provided test, copied byte-identical. It has not been run: a case that fails on its own logic and not on a
  missing name is reported as `121` in the report, not edited.
- `test_forms_rules_format1.py`: the format 1 half of `docs/tickets/P2-INSP/provided/T00_test_insp_rules.py`, made by
  `sed -n '1,/^# ---- failed_questions/p' <that file> | head -n -1 | sed 's/from tl_mod_quality import insp_rules as r/from tl_core.forms import rules as r/'`
  (everything before the `failed_questions and result_of` section; the helper and imports stay). Commit the result.
- `test_forms_contract.py`: `TemplateRef` and `FormBinding` refuse an unknown key, a hash that is not 64 lower hex,
  `available=True` without command, a `reason` with `available=True`, a `fixed_args` key equal to `answers_arg`;
  the registry refuses two sources for one type, a non-conforming source and more than 32, and loads an empty group
  as `{}`; `tl_core.forms` imports no `tl_api`, `tl_cli`, `tl_mcp`, `tl_tui`, `tl_web` or `tl_mod_*` module
  (walk `sys.modules` after a fresh import, as `test_qr_contract.py` does).

## Gate
`just check` (with `NODE_OPTIONS=--max-old-space-size=6144`); then one run:
`just gate packages/tl-core/tests/test_forms_rules.py packages/tl-core/tests/test_forms_rules_format1.py packages/tl-core/tests/test_forms_contract.py packages/tl-core/tests/test_qr_contract.py packages/tl-core/tests/test_readiness_registry.py`
(the last two prove the sibling registries are untouched). No Postgres run: no adapter or SQL is touched. Existing
paths checked with `ls` on `p2/ip` @b91ee33d; the three `test_forms_*` files are created by this piece.

## Mutation cap
One sentinel plus at most 5 targeted mutants on `rules.py`: `MAX_CONDITION_DEPTH` bound removed; a leaf may name a
later field; a hidden field counts as answered for later conditions; `visible_ids` ignored by `validate_answers`
(answer to a hidden field accepted); `content_hash` ignores field order. 3 lines in the report.

## Report
Builder return ≤ 15 lines; report ≤ 60 lines at `docs/reports/P2-FORMS/S1.md`; first line: deviations or none, and
whether the provided test copy is byte-identical. List the final public names (types, functions, constants) as one
table for S3, the projection tickets and T13. Commit `P2-FORMS-S1: ...` with the session trailers; no model names in
committed text.

## Amendment 1 (orchestrator, 2026-11-15)
The spec text wins: photo answers are 1 to MAX_PHOTOS distinct ULIDs. The provided test case `[ULID] * 10` is replaced
with ten distinct ids, the eleven-id case uses distinct ids, and a duplicate pair is added as invalid. The provided copy
`docs/tickets/P2-FORMS/provided/S1_test_forms_rules.py` is updated to the same bytes.

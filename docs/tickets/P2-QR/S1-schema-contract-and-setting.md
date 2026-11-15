# P2-QR S1 — Module `qr`: schema, settings, words, skeleton, and the frozen status-card contract

kind: piece
review: full
branch: p2/qr-s1-schema-contract
worktree: /home/user/wt/qr/s1
Depends on: `p2/ip`. Gated: schema, settings, access words, core interface (APPROVALS lines before merge; ADR-0030
accepted first). Labels: schema, core.

## Why
`docs/build-spec/specs/qr-workface.md` §2, §3, §9, §10 and ADR-0030: a printed QR holds an opaque code; the server
keeps only its hash in a ledgered record; a scan shows a status card that the record's own module supplies. Nothing
of this exists: there is no `qr` module, no `api.public_base_url` (dropped from P2-I5), no card contract. Every other
P2-QR item, and one ticket each in P2-INSP and P2-PTW, is written against the names this piece freezes.

## Goal
1. **Schema** `schema/modules/qr/` (`module.yaml`, `scan_code.yaml`, `events.yaml`; copy conventions from
   `schema/modules/quality/`). Class `ScanCode`: record type `qr.ScanCode`, table `cur_qr_scan_code`, `tl:offline: none`,
   no workflow, no numbering pattern (a code has no project key; its id is the record id).
   Fields: `id`, `scope`, `code_hash` (64 lower hex, required, unique index), `target_id` (indexed; the
   confidentiality subject), `target_type` (≤ 64), `label_text` (≤ 40, null ok), `size` (enum `LabelSize` tag, card,
   sheet), `issued_by` (actor text ≤ 64), `issued_at`, `expires_on` (date, null ok), `revoked_at`, `revoked_by`,
   `revoke_reason` (≤ 300), `replaced_by_id`.
   Events (`feed_policy: none`, each payload names `record_id`): `ScanCode.Issued` {code_hash, target_id, target_type,
   label_text, size, expires_on}, `ScanCode.Revoked` {reason, replaced_by_id}. No field anywhere holds the code.
   Valid time: tag nothing; add the two events to `tests/tools/valid_time_baseline.toml` with the reason "a system
   act, transaction time is the fact".
2. **Settings** in `schema/settings/platform.yaml`:
   `api.public_base_url` (string, default empty, scopes `[platform]`, not lockable, pattern
   `^$|^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?$|^http://(localhost|127\.0\.0\.1)(:[0-9]{1,5})?$`; docs say: the public
   address of the web client; printing a QR label is refused while empty; changing it orphans printed labels);
   `qr.codes_per_record_max` (int, default 20, 1..100, scopes `[platform, company, project]`, lockable).
3. **Access words** (`schema/settings/access-words.yaml`, a `qr:` block): `qr.view: read`, `qr.issue: user`,
   `qr.revoke: controller`.
4. **Package** `packages/tl-modules/qr` (`tl-mod-qr`, `tl_mod_qr`; copy the skeleton of `packages/tl-modules/quality`):
   `pyproject.toml` (entry point `throughline.modules` / `qr`; optional extra `labels = ["segno"]`, declared only, not
   installed by default), `README.md`, `AGENTS.md`, `__init__.py` (`MODULE = "qr"`), `names.py` (record type, the
   three words, event names), `projectors/` (the `ScanCode` projector: Issued inserts, Revoked sets the three revoke
   fields and `replaced_by_id`), `module.py` `spec()` with `record_types`, `projectors`, `command_words={}`,
   `proposable=()`, no generic commands on `qr.ScanCode`, no hook fields (S2 adds them).
5. **Contract** `packages/tl-core/src/tl_core/qr/types.py` (frozen once merged; module docstring says so, in the
   style of `tl_core/readiness/types.py`) and `tl_core/qr/registry.py`:
   - `SCAN_CARD_ENTRY_POINT = "throughline.scan_cards"`; bounds `MAX_LINES = 8`, `MAX_LABEL_CHARS = 24`,
     `MAX_VALUE_CHARS = 80`, `MAX_BANNER_CHARS = 40`, `MAX_TITLE_CHARS = 120`, `MAX_PROVIDERS = 32`.
   - `Tone = Literal["go", "caution", "stop", "neutral"]`.
   - `class ScanLine(BaseModel)`: `label`, `value` (bounded).
   - `class ScanCard(BaseModel)`: `record_type`, `key`, `title`, `banner`, `tone: Tone`, `as_of: datetime` (aware),
     `valid_until: datetime | None`, `lines: list[ScanLine]` (≤ `MAX_LINES`), `open_path: str | None` (a path that
     starts with `/web/`, else refused). `extra="forbid"`.
   - `class ScanCardProvider(Protocol)` (runtime checkable): `record_type: str`, `view_word: str`,
     `def card(self, conn: Connection, record_id: str, viewer: Viewer, now: datetime) -> ScanCard | None`. Docstring
     rules: a pure read; never writes; never raises for a bad or hidden record (answers `None`); `None` for a record
     the viewer cannot see; never opens the network.
   - `registry.load_scan_cards() -> dict[str, ScanCardProvider]` keyed by record type: loads the entry-point group; a
     plugin that fails to load is an error at first use; two providers for one record type is an error; more than
     `MAX_PROVIDERS` is an error. Follow `tl_core/readiness/registry.py`.
   No `tl_core/modules.py` change (P2-X4 owns that file).
6. `just gen`, `just compat-update` (additive); commit sources and generated output together.

## Allowed paths
- `schema/modules/qr/**` (create); `schema/settings/platform.yaml` (two keys); `schema/settings/access-words.yaml`
  (the `qr:` block); `tests/tools/valid_time_baseline.toml` (lines); `docs/build-spec/specs/offline-classes.md` (one row)
- `packages/tl-schema/src/tl_schema/generated/**` (`just gen` output only); `packages/tl-schema/compat/event-schemas.json`
- `packages/tl-modules/qr/**` (create, as listed in Goal 4, plus `tests/conftest.py`, `tests/test_module_spec.py`,
  `tests/test_projector.py`)
- `packages/tl-core/src/tl_core/qr/{__init__,types,registry}.py` (create); `packages/tl-core/tests/test_qr_contract.py` (create)
- root `pyproject.toml` (workspace source, test path, dependency line) and `uv.lock`; one dependency line
  `"tl-mod-qr"` in `packages/tl-{api,cli,mcp,tui,web}/pyproject.toml`
- `packages/tl-schema/tests/test_qr_schema.py` (create)
- Pinned lists, union form, each named in the report: `packages/tl-schema/tests/test_offline_classes.py` (count + 1),
  `test_ddl.py`, `test_generate.py`, `test_ddl_views.py`, `packages/tl-core/tests/auth/test_access_words.py` (add a
  `QR` set of three to the sum), `tests/services/test_modules.py` (module list), `tests/settings/test_phase2_keys.py`
  and `packages/tl-core/tests/test_settings_definitions.py` (the two keys), and any other test that fails only because
  the module, words or keys now exist
- `docs/reports/P2-QR/S1.md` (create)
Not allowed: commands, handlers, views, routes, CLI, MCP, TUI, web; `tl_core/modules.py`; `tl_core/confidentiality.py`
(S2); any other module.

## Tests to add
- `packages/tl-schema/tests/test_qr_schema.py`: the class, table, unique index on `code_hash`, the two event types,
  offline class `none`; no slot of the class or of either payload is named `code`, `token` or `url`.
- `packages/tl-modules/qr/tests/test_module_spec.py`: the module loads; one record type; no proposable; no generic
  commands. `test_projector.py`: Issued then Revoked give the expected row; a rebuild gives the same row.
- `packages/tl-core/tests/test_qr_contract.py`: `ScanCard` refuses a ninth line, an over-long label, value, banner
  and title, a naive `as_of`, an unknown tone, an unknown field, an `open_path` that does not start with `/web/` or
  that contains `//` or `..`; the registry refuses two providers for one type and a provider that does not satisfy the
  protocol, and loads an empty group as `{}`; `tl_core.qr` imports no web, CLI, MCP or module code.
- Settings: `api.public_base_url` accepts `https://tl.example.com`, `https://tl.example.com:8443`,
  `http://localhost:8000`, empty; refuses `http://tl.example.com`, a trailing slash, a path, a query, `user@host`.

## Gate
`just check` (with `NODE_OPTIONS=--max-old-space-size=6144`); then
`just gate packages/tl-schema/tests/test_qr_schema.py packages/tl-schema/tests/test_offline_classes.py packages/tl-schema/tests/test_ddl.py packages/tl-schema/tests/test_ddl_views.py packages/tl-schema/tests/test_generate.py packages/tl-schema/tests/test_compat.py packages/tl-schema/tests/test_valid_time_tag.py`
and
`just gate packages/tl-core/tests/test_qr_contract.py packages/tl-core/tests/auth/test_access_words.py packages/tl-core/tests/test_settings_definitions.py packages/tl-core/tests/test_readiness_registry.py tests/settings/test_phase2_keys.py tests/services/test_modules.py tests/services/test_modules_offline.py packages/tl-modules/qr/tests`
(two runs, one at a time). `just gate-pg packages/tl-modules/qr/tests` for the projector. The existing paths above
were checked with `ls` on trunk @d4e92ffc; the three `qr` paths are created by this piece.

## Mutation cap
One sentinel plus at most 4 targeted mutants: `MAX_LINES` bound removed; `open_path` prefix check removed; duplicate
provider accepted; settings pattern accepts plain `http://` for a non-local host. 3 lines in the report.

## Report
Builder return ≤ 15 lines; report ≤ 60 lines at `docs/reports/P2-QR/S1.md`; first line: deviations or none; list
every pinned file changed with old and new count. Commit `P2-QR-S1: ...` with the session trailers; no model names
in committed text.

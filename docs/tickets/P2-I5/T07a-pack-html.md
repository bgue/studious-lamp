# P2-I5-T07a — IWP pack: data assembly, HTML with inline QR, `tl awp iwp pack`

Status: ready (S2 merged; reads only module code, not the client; may run in the first wave)
Tier: haiku
Kind: ticket
Review: full
Labels: awp, cli, security
Depends on: S2
Branch: `p2/i5-t07a-pack`
Worktree: harness-created under `/home/user/wt/i5/t07a` (from `p2/i5` head)

## Goal
`tl awp iwp pack NUMBER` writes the work pack of one IWP as one HTML file a foreman can print: cover, scope and steps, drawings with a QR code each (inline SVG, only when `segno` is installed), the take-off lines, placeholders, the sign-off sheet. With `--attach` the file is stored in the IWP's file slot `pack`. Everything shown is read through the viewer's class filter; a hidden record is simply absent.

## Brief references (pasted; D4, D26)
- Dependencies: none added. `segno` is the optional extra `pack` (`uv sync --extra pack`); import it inside `render_html` in a `try`; missing: no QR, and `notes` holds `QR codes not drawn: the pack extra is not installed.` and the CLI prints it as `note: ...` and still writes the file. No Jinja2 (not a dependency of this package, D26): the template is a repository file `tl_mod_awp/pack_template.html` read with `importlib.resources`, filled by `string.Template.substitute`; every value that comes from a record goes through `html.escape(str(v), quote=True)` in ONE helper before it reaches the template (`_e`); the table fragments are built by one `_table(columns, rows)` over escaped cells. The template never receives a raw value. T07b writes the real template; here it is the minimal one named below.
- `PackData` (frozen dataclasses, built by `build_pack_data(conn, scope, number, viewer) -> PackData`, `RecordNotFoundError` for a missing, hidden or void IWP, one text): `cover` (number, title, state, discipline, foreman, cwp number, planned start and finish, estimated hours, crew text), `scope` (the `iwp_views.iwp_scope` rows and, per item, the steps earned from `engine.earned_fraction(conn, id, viewer=viewer)`: key, pct, steps), `drawings` (active links from the IWP with a pin: document key, title, pin, one SQL over `cur_links l JOIN cur_core_record d ON d.id = l.to_id` with `not_hidden("l.to_id", viewer)`; `l.pin IS NOT NULL AND l.status = 'active'`), `mto` (`cur_materials_mto_line WHERE work_package_id = :iwp` by `line_no`: line, item key via `cur_core_record`, qty, uom, reserved, issued; the table by name literal as `readiness/hooks.py` does, skipped when `has_table` is false; hidden lines and items dropped), `signoffs` (`IwpDetail.signoffs`: who, role, day; never the record hash), `generated_on` (a `date` argument, default today, so a test pins it).
- Placeholders in the data, text only: safety and ITP quality `"No safety plan attached yet."`, `"No inspection and test plan attached yet."`; permits and scaffold tags `"not tracked yet"` (until I4-B; T07a reads nothing for them).
- QR payload is the document key text (a record key, never a URL, never an id); `segno.make(key, error="m").svg_inline(scale=2, border=1)`; the key is also printed under the code.
- CLI (`tl_cli/awp_pack.py`, `register(iwp_app)`): `pack NUMBER [--out FILE] [--attach] [--project P] [--actor A]`; default out `<number>.html` in the current directory; the file is created with mode 0600 and replaced if present; prints `pack <number>  <bytes> bytes  qr <yes|no>` then `note: <text>` lines; with `--attach` then `slot pack  file <file id>` through `tl_cli.corr.upload(db, scope, actor, record_id, "pack", path)` (read it: the item's upload guard applies; if the guard refuses an IWP, write the answer under Blocked). Reads use `session_viewer(db)`.

## Interfaces (verbatim from repo)
```python
# tl_mod_awp/iwp_views.py
def iwp_detail(conn, scope, number) -> IwpDetail | None; def iwp_scope(conn, scope, number, *, limit=500) -> list[ScopeRow] | None
# tl_mod_awp/progress/engine.py
def earned_fraction(conn, iwp_id, *, viewer=None) -> Earned
# tl_core.confidentiality
def not_hidden(column: str, viewer: Viewer | None = None) -> tuple[str, dict[str, Any]]
```
Minimal template slots, in this order (T07b keeps them): `$cover $scope $drawings $mto $safety $quality $permits $signoff $generated`.

## Context (read these, nothing else)
- `packages/tl-modules/awp/src/tl_mod_awp/{iwp_views.py (36-80, 182-250), progress/engine.py (95-122, 395-416), readiness/hooks.py (30-50)}`, `packages/tl-cli/src/tl_cli/{awp_progress.py (T04b pattern), corr.py (94-125)}`
- `schema/fixtures/files/awp-iwp.yaml` (the `pack` slot), `docs/reports/P2-I5/{S2,T04b}.md`

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/pack.py` (create), `packages/tl-modules/awp/src/tl_mod_awp/pack_template.html` (create, minimal), `packages/tl-modules/awp/pyproject.toml` only to add the template to the package data if the build needs it
- `packages/tl-cli/src/tl_cli/awp_pack.py` (create), `packages/tl-cli/src/tl_cli/awp.py` (one import and `awp_pack.register(iwp_app)` after `awp_progress.register(iwp_app)`)
- `packages/tl-modules/awp/tests/test_pack.py`, `packages/tl-cli/tests/test_awp_pack.py` (create)
- `docs/reports/P2-I5/T07a.md`; consequential pins (union): `docs/reference/awp.md` (one CLI line)

## Acceptance
```
just check
just gate packages/tl-modules/awp/tests/test_pack.py packages/tl-cli/tests/test_awp_pack.py packages/tl-cli/tests/test_cli_awp.py
uv sync --extra pack && just gate packages/tl-modules/awp/tests/test_pack.py
```
The pack extra run proves the QR path; the plain run proves the missing-library path (a test patches the import to fail).

## Tests to add
`test_pack.py` (World as `test_week.py`): the cover and scope rows equal the views; a scope item with a recorded step shows it; a pinned document is a drawing, an unpinned link is not; a hidden document (test source as `provided/T03` `hidden`) is absent and nothing of it is in the HTML; a title `<script>x</script>` and `"&` come out escaped; HTML holds no record id (assert none of the ids appear); with `segno` an `<svg` appears per drawing, without it none and the note is present; the same call twice with one `generated_on` is byte-equal. `test_awp_pack.py` (pattern of `test_awp_progress.py`): `pack` writes the file (mode 0600), prints the two lines, an unknown number is `error: no IWP <n>` exit 1 and writes nothing, `--attach` stores a file in slot `pack` (a second run replaces the current file), no `Traceback`.

## Escalation triggers
- `segno` has no `svg_inline` in the locked version; the upload guard refuses an IWP; a template read needs a package-data change beyond `pyproject.toml`.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths listed. Commit subjects `P2-I5-T07a: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)

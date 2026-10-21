# P1-UX-T12b — Tour section 23: Plain language and the record screen

Status: ready (staged: dispatch after T12 is merged)
Tier: haiku
Kind: ticket
Review: full
Labels: docs, tui
Depends on: T12 (merged)
Branch: `p1/ux-t12b-tour-section`

## Goal
The Phase 1 tour has a new section 23, "Plain language and the record screen": the tour world sets values of `document_data`, `rfi_data` and `correspondence_data` (F7), the record screen is shown opened from each register with its Properties tab, and the Ctrl+D toggle is shown on and off as an admin. `PHASE-1-TOUR.md` gets the matching section; a second run changes no file.

## Brief references (pasted)
> SCOPE 5: "a new short section in PHASE-1-TOUR.md shows the record screen opened from each register with its properties, and the technical-details toggle on and off."
> Sets: `document_data` (originator, area, system, confidentiality_note, native_format, review_due) on documents; `rfi_data` (location, drawing_ref, trade, cost_estimate, cost_currency, schedule_impact_days) on RFIs; `correspondence_data` (contract_clause, other_party_ref, response_required_by, delivery_method) on letters and commercial notices. Set values with `ws.tl("pset", "set", "--project", "P123", KEY, PSET, "name=value", ...)`.

## Interfaces (verbatim from repo)
```python
# dev/tour/phase1.py
def build_app(ws, *, admin=False, actor="user:demo", controller=False) -> Any      # TlApp over the tour ledger
def section_legacy_load(ws: Workspace) -> None                                       # last section today (22); main() calls the sections in order
# tourkit: shot_tui(ws, app, name, title, *needles); until(pilot, pred, what); settle(pilot, n); run_tui(ws, app, scenario, size=(160, 48))
# pattern: section_register_tui (phase1.py ~611): app = build_app(ws); async def scenario(pilot): await pilot.press("f7"); await tk.until(...); tk.shot_tui(...); tk.run_tui(ws, app, scenario, size=(160, 48))
# record screen: Enter on a register row; press "2" for Properties; Esc closes. Ctrl+D (admin only): "Technical details on" / "Technical details off".
```

## Context (read these, nothing else)
- `dev/tour/phase1.py` (lines 611-670 `section_register_tui`; 2005-2058 `main`; and the keys/records of sections 16-18: `section_schedules`, `section_correspondence`, `section_rfi` headings only)
- `docs/reports/PHASE-1-TOUR.md` (section 22 as the model; the contents table at the top; the "What Phase 1 did not do" heading)
- `docs/reports/tour/index.html` (check it needs no change: it lists documents, not screenshots)

## Allowed paths
- `dev/tour/phase1.py`
- `docs/reports/tour/phase-1/23*.svg` (create)
- `docs/reports/PHASE-1-TOUR.md`
- `docs/reports/P1-UX/T12b.md` (create)

## Steps
1. `section_plain_record_screen(ws)` after `section_legacy_load` in `main()` (print `"P1-UX: plain language and the record screen"`). First, set the three sets' values on existing tour records: a document (`ISO-1234`), an RFI and a letter from sections 17-18, with conforming values (codes from the standards file); the CLI prints `conformance`: `expect` it is not a failure. Doing it here leaves sections 1-22 unchanged except through plain language.
2. Screens, each with `tk.shot_tui` needles: `23a` document register, Enter, Properties (`Document data`, `Originator`); `23b` tag register record (its class set); `23c` RFI log record (`RFI data`, `Trade`); `23d` correspondence register record (`Correspondence data`, `Contract clause`); `23e` as demo (admin): the record screen Details in plain words; `23f` Ctrl+D on: the same Details with ids, versions and keys (needle `Technical details on`); `23g` Ctrl+D off again. Add commercial and schedule only if the tour world already has rows for them.
3. `PHASE-1-TOUR.md`: add row 23 to the contents table and `## 23. Plain language and the record screen` before "What Phase 1 did not do", in the style of section 22: one image per screenshot with a one-sentence alt text, 2 short paragraphs, **Reproduce:** `just demo P1-UX`, **Standard activity** / **Novel approach** / **Honest limits** sentences (limits: display only; the sets are examples in the fixture standard; the toggle is admins only and not remembered). Update the "Screenshots" count text if the file states one.
4. Run `just tour 1` twice; the second run changes no file.

## Acceptance
```
just check
just tour 1
git status --short docs/reports
just tour 1 && git status --short docs/reports
```
Expected: `23a` to `23g` (or fewer, named in the report) are new; the second `git status` equals the first. Paths: `dev/tour/phase1.py`, `PHASE-1-TOUR.md` exist; the SVGs are (new). No pytest gate.

## Tests to add
None.

## Report requirements
Standard report; list the SVGs created, the values set (one line each), any screen left out and why.

## Escalation triggers
- A set value is refused: report the message; do not edit the schema.
- A register has no row in the tour world for a type: skip its screenshot and say so.
- The second run differs: report the file; do not commit it.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)

# P1-UX-S4: demo and re-shot tours, with the leak check in the tour (piece)

kind: piece · review: full · branch p1/ux-s4-demo-and-tours · depends on T11 merged
Supersedes T11c, T12 and T12b (orchestrator decision D45, owner request 2026-10-21 to streamline): one builder
does the demo and both tours in one pass, and the tour itself checks every screen it captures for technical text.
Read T11c-demo.md, T12-tours-regen.md and T12b-tour-section.md in this folder for the detail of each part;
where they disagree with this file, this file wins.

## Goal
1. `dev/demos/P1-UX.sh` (`just demo P1-UX`, SQLite and Postgres, same structure as `dev/demos/P1-I8.sh`) proving
   SCOPE.md demo clauses 1-4, as T11c describes. Clause 2 runs `packages/tl-tui/tests/test_plain_walk.py` (T11)
   and adds the plain-user refusal check on the real ledger.
2. Both tours regenerated (`just tour-all`), narratives that quote changed screen text updated, as T12 describes.
3. PHASE-1-TOUR.md section 23 "Plain language and the record screen", screenshots 23a-23g, with values for
   `document_data`, `rfi_data` and `correspondence_data` on existing tour records, as T12b describes.
4. **Leak check inside the tour (new).** `dev/tour/tourkit.py` gets one function that takes a captured screen's
   text (the SVG text, or the terminal text for CLI captures of TUI screens only), runs
   `tl_tui.display.find_technical(text, labels)` and records any hit. Every TUI screenshot in phase0.py and
   phase1.py goes through it, except the technical-mode shots of section 23 (marked explicitly). The tour exits
   non-zero and prints `LEAK <shot> <tokens>` if a plain screenshot carries technical text. CLI and API output
   shots are not checked (their output is unchanged by design, SCOPE Constraints).

## Rules for this piece (the streamlined process, D45)
- Consequential pins: if a test or snapshot outside these paths breaks only because a screen now shows the
  intended plain words, update it in this piece, add or keep a technical-mode counterpart, and list each such
  file in the report. Do not stop to ask for that.
- A real leak found by the tour check in a screen's text module: fix it with a label or `mode_of` call in that
  `*_text.py` file and a test; anything larger goes in the report as a follow-up.
- Run only: `just check`, `just gate packages/tl-tui/tests` once at the end, `just demo P1-UX`, `just tour-all`
  twice (the second run must change no file). No other demos.

## Allowed paths
dev/demos/P1-UX.sh, dev/demos/p1_ux_demo.py (or the helper layout P1-I8 uses), justfile (demo entry only if the
existing `demo` recipe needs one), dev/tour/**, docs/reports/PHASE-0-TOUR.md, docs/reports/PHASE-1-TOUR.md,
docs/reports/tour/**, packages/tl-tui/src/tl_tui/*_text.py (leak fixes only), packages/tl-tui/tests/** (consequential
pins and the tests of leak fixes), docs/reports/P1-UX/S4.md.

## Acceptance
- `just demo P1-UX` ends with `P1-UX demo OK on: sqlite postgres`.
- `just tour-all` prints no `LEAK` line, exits 0, and a second run leaves `git status` clean.
- `just check` clean; `just gate packages/tl-tui/tests` ends `gate: PASS`.
- Report docs/reports/P1-UX/S4.md (≤ 60 lines): demo clause lines, screenshot count per tour, leak fixes, the
  consequential pins changed, follow-ups.

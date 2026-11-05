# P2-WEB1-T23 — Three small polish items seen in the web look v2 screenshots

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: web
Depends on: S7, T21, T22 (merged).
Branch: `p2/web1-t23-look-polish`   (from p2/web1)

## Goal (spec `docs/build-spec/specs/web-look-v2.md`)
1. **Sign-in heading inside the card.** `templates/sign_in.html` puts `<h1>Sign in</h1>` above the form, so it sits
   outside the centred card (the card is drawn on the form). Wrap the heading, the error line and the form in one
   `<div class="tl-card tl-sign-in">`, and in `static/tl.css` move the card look (surface, border, radius, shadow,
   28px padding, 360px, centred 12vh from the top) from the form rule to `.tl-sign-in`; `h1` there is 20px 600,
   margin 0 0 16px. Keep every input id, name and the form action.
2. **Status line separators.** The summary line comes from the terminal text and uses ` | ` between facts
   ("5 items | answered 0 | open 5"). On the web, show ` · ` instead: in `log.py` where the status text is built
   (`text=notice or summary`), replace ` | ` with ` · ` in the summary only (not in a notice). One helper in
   `present.py`, `web_summary(text: str) -> str`.
3. **Stock panel badge slot.** `tl_tui.materials_text` builds the stock page with
   `state=f"Lot {key} · receipt {receipt}"`, so the web shows that line as a grey badge. In `pages/stock.py`
   `panel_page`, return the page with that text moved into `summary` (prefixed to the existing summary with ` · `)
   and `state=""` (use `dataclasses.replace`). Do not change `materials_text.py` (the terminal keeps its line).

## Allowed paths
- `packages/tl-web/src/tl_web/templates/sign_in.html`, `static/tl.css`, `log.py`, `present.py`, `pages/stock.py`
- `packages/tl-web/tests/**`
- `docs/reports/P2-WEB1/T23.md` (create)

## Steps
Make the three changes; update tests that pin the old markup or the ` | ` summary; add one test per item. Re-take
the screenshots (`uv run pytest packages/tl-web/tests -k screenshot -q`) and Read `T12-stock.png`; say what changed.

## Acceptance
- `NODE_OPTIONS=--max-old-space-size=6144 just check` exit 0
- `just gate packages/tl-web/tests | tail -45 | tee .gate/summary.txt` ends `gate: PASS`

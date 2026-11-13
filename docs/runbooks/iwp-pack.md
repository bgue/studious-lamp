# Runbook — the IWP work pack: write one printable HTML file of an IWP, with QR codes for its drawings

Purpose: give a foreman one printable HTML file for an interim work package (IWP): its cover, scope and steps, pinned drawings with QR codes, take-off, safety, inspection and test plan, permits and the sign-off. `tl awp iwp pack` writes it; `--attach` also stores it in the IWP's `pack` file slot. Module reference: `packages/tl-modules/awp/README.md`.

## When to use
- Trigger: a crew needs the IWP on paper or on a tablet for the week's work.
- Trigger: the pack slot of an IWP must hold the current pack (for example after a scope change).

## Before you start
- Access: `awp.view` (read). `--attach` stores the file through the document upload path (`corr.upload`), so the upload rules of that path apply to the person who runs it.
- The IWP must exist and be visible to you. A hidden or unknown IWP is `error: no IWP <number>`, exit 1, and no file is written.
- QR codes need the optional `pack` extra (`segno`). Install it from the repository root with `uv sync --all-packages --extra pack`. Without it the file is written with no codes and a note says so.
- Every command takes `--project P123`. Use `--db` or `TL_DB` for the ledger; never print a `postgresql://` URL.

## Steps

### 1. Write the pack
```
uv run tl awp iwp pack P123-IWP-PIP-0001 --project P123 --out P123-IWP-PIP-0001.html
```
Expected:
```
pack P123-IWP-PIP-0001  <bytes> bytes  qr <yes|no>
note: <text>        (one line per note; none when all is drawn)
```
The file is written with mode 0600. Without `--out` the file is `<number>.html` in the current directory. An existing file at the path is replaced.

### 2. Attach the pack to the IWP (optional)
```
uv run tl awp iwp pack P123-IWP-PIP-0001 --project P123 --out P123-IWP-PIP-0001.html --attach
```
Expected: the same lines, then `slot pack  file <id>`. A second `--attach` supersedes the first in the slot. The file service keeps identical bytes once: attaching a pack with the same content as the one in the slot adds no revision, so a replacement must change the content (for example after a scope change).

## What the HTML holds
The sections, in order, each from the viewer's own reads (a hidden record is absent and nothing of it reaches the page):

| Section | Content |
|---|---|
| Cover | the IWP number, title, state, discipline, foreman, CWP, planned start and finish, estimated hours and crew |
| Scope and steps | the scope items by type, with their steps |
| Drawings | the pinned documents; a QR code per drawing when the `pack` extra is installed; "No drawings pinned." otherwise |
| Take-off | the materials take-off lines: line, item, quantity, unit, reserved, issued (empty table when the IWP has none) |
| Safety | the fixed text "No safety plan attached yet." in this release |
| Inspection and test plan | the fixed text "No inspection and test plan attached yet." in this release |
| Permits and scaffold tags | the fixed text "not tracked yet" |
| Sign-off | who, role and day of each sign-off on the IWP |

Every value from a record is escaped before it reaches the page. The page holds no record id and no URL.

## The QR code
- A QR code carries the document key (a record key), never a URL and never a record id.
- With the `pack` extra missing, the pack is still written; the note `QR codes not drawn: the pack extra is not installed.` says so.

## Verify
- `uv run tl awp iwp show P123-IWP-PIP-0001 --project P123` shows the IWP the pack was written from.
- Open the HTML file in a browser: the sections above appear in order, and each pinned drawing has a code when `qr yes` was printed.
- With `--attach`, the line `slot pack  file <id>` is printed.

## Known limits
- The page is a snapshot of the reads at the time it is written; a later change to the IWP needs a new pack.
- Safety, inspection and permits show their fixed text: no command records them yet.

## Roll back
- The HTML file is a local file: delete it on the machine where it was written.
- An attached pack stays in the file service; the next `--attach` with a different pack supersedes it in the slot.

## Related
- `docs/runbooks/iwp-readiness.md` (the IWP's constraints, sign-off and issue), `docs/runbooks/weekly-cycle.md` (committing the IWP to a week), `docs/reference/awp.md` (the pack command line and its code).

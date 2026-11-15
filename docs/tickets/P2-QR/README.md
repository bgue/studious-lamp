# P2-QR — QR codes at the workface: scan codes, status cards, labels

Status: planning (r0 written by the orchestrator, 2026-11-15; nothing dispatched). 3 pieces, 12 tickets.
Sources: `docs/build-spec/specs/qr-workface.md`, ADR-0030 (proposed), owner request 2026-11-15.
Branch `p2/qr` from the integration branch `p2/ip`. Worktree `/home/user/wt/p2-qr`. Piece branches `p2/qr-s<n>-<slug>`,
ticket branches `p2/qr-t<nn>-<slug>`, worktrees `/home/user/wt/qr/<id>`. Board: `STATE.md` (round 1 writes it).
This file also holds the fan-out across P2-QR, P2-INSP and P2-PTW (last section).

## Objective
After this increment a person who can see an IWP or a scaffold prints a label for it (CLI, terminal, web); a phone
scan of the label opens a sign-in-protected status page that says what the record's state is now; a label can be
revoked or rotated; and any module can add its record type by shipping one status-card function over a frozen
contract. P2-INSP and P2-PTW add the inspection and permit cards. Out of scope: anonymous scans, actions from the
scan page, PDF labels, phone-side offline, changing the IWP pack's QR.

## Demo (`dev/demos/P2-QR.sh`, `just demo P2-QR`, both adapters)
1. With `api.public_base_url` unset, `tl qr label <IWP key>` is refused with the fixed message; after setting it, the
   command writes a label file whose QR text is `<base>/q/<16 chars>` and contains no key, id or project code.
2. Signed out, `GET /q/<code>` and `GET /q/<nonsense>` give the same sign-in response. Signed in as a reader who can
   see the IWP, the page shows the state banner, key, "as of" time and lines.
3. Five misses, one answer: unknown, revoked, expired, hidden record, no view word: byte-identical 404 pages.
4. Rotate: the old code is a miss, the new one resolves; `tl qr ls <key>` shows both rows and never a code.
5. Scaffold card (when P2-I4B is on the trunk): a red tag shows the stop banner; else the clause prints `deferred`.
6. An agent token gets the miss on `/q/…` and on the code register. `tl qr export --format jsonl` rows equal `tl qr ls`.
7. `tl qr resolve <code>` on an embedded ledger prints the same card text.

## Checkpoints
C1: S1 merged to `p2/ip` (schema, setting, words, frozen card contract; APPROVALS). C2: S2 and S3 merged (code
service, scan page). C3: every ticket merged or abandoned. C4: per-folder gates on touched packages, `gate-pg` on
touched directories, demo on both adapters, tour shots, security review closed.

## Items
Tier B = builder piece (`kind: piece`); H = implementer ticket. Sec = a row for the wave's security review.

| ID | Title | Tier | Depends | Sec | Review |
|---|---|---|---|---|---|
| S1 | Schema `schema/modules/qr/` (`qr.ScanCode`, two events), settings `api.public_base_url`, `qr.codes_per_record_max`, three words, module skeleton, the frozen contract `tl_core/qr/types.py` and registry | B | `p2/ip` | yes | full |
| S2 | Code service and commands: generate, hash, `IssueScanCode` (refused without the base address), `RevokeScanCode`, `RotateScanCode`, `resolve()` with one exit for every miss, subject part in `confidentiality.py`, hooks declared, exclusions; sentinel + ≤ 5 mutants | B | S1 | yes | full |
| S3 | Scan page `/q` and `/q/{code}` in the web client: sign-in bounce before any lookup, byte-identical miss, rate limit, `no-store` and `no-referrer`, code stripped from the access log, the five-reader walk | B | S2 | yes | full |
| T01 | Read views `tl_mod_qr/views.py`: `codes_for_record`, `code_counts`, `export_rows(rows, "csv"\|"jsonl")` | H | S2 | — | full |
| T02 | Label renderer `tl_mod_qr/labels.py` (pure: URL, text, size → HTML with inline SVG; fixed note without `segno`), provided test | H | S1 | — | lite |
| T03 | Card contract test helper `tests/contract/test_scan_card_contract.py::check_scan_card_contract` and a fake provider | H | S1 | — | full |
| T04 | Card `awp.IWP` (`tl_mod_awp/scan_card.py`, entry point) | H | T03 | yes | full |
| T05 | Card `scaffold.Scaffold` (`tl_mod_scaffold/scan_card.py`, entry point) | H | T03, P2-I4B on trunk | yes | full |
| T06 | API read router (`GET /qr/codes`, `/qr/codes/export`, JSON `GET /qr/resolve/{code}`) in the module package, five-reader walk | H | T01 | yes | full |
| T07 | CLI group `tl qr`: `label`, `sheet`, `ls`, `revoke`, `rotate`, `resolve`, `export` | H | T01, T02 | — | full |
| T08 | Client methods and fakes | H | T06 | — | full |
| T09 | Terminal: `qr_text.py` and the "Print label" action on the record screen | H | T08, T02 | — | full |
| T10 | Web "Print label" form on the scan page and record page (existing action machinery, CSRF) | H | S3, T02 | yes | full |
| T11 | Demo `dev/demos/P2-QR.sh` and driver | H | T04–T10 | — | full |
| T12 | Tour shots (scan page at phone width for each tone, label sheet, terminal action) and docs: module README and AGENTS, runbook `docs/runbooks/qr-labels.md`, root `AGENTS.md` row | H | T11 | — | lite |

## Waves (implementer tickets in one wave have disjoint paths; gates name test files, never a whole package)
| Wave | Runs together | Notes |
|---|---|---|
| 1 | S1 | Alone on shared pins and generated files |
| 2 | S2 ∥ T02 ∥ T03 | T02 and T03 need only S1's names |
| 3 | S3 ∥ T01 ∥ T04 ∥ T05 | Three module folders and the web folder |
| 4 | T06 ∥ T07 ∥ T10 | Module routes file, `tl_cli` file, web templates |
| 5 | T08, then T09 | Client then screen |
| 6 | T11, then T12 | |
At most two heavy test runs on the box at once: the gate runner takes tickets two at a time; a wave of four implementer
tickets is four authors and two gate slots.

## APPROVALS lines needed before merge (the orchestrator never self-approves; the owner or a delegation does)
- S1 · schema merge `schema/modules/qr/**` (new module, additive).
- S1 · settings `api.public_base_url`, `qr.codes_per_record_max`; access words `qr.view`, `qr.issue`, `qr.revoke`.
- S1 · core interface `tl_core/qr/types.py` and entry-point group `throughline.scan_cards` (ADR-0030 accepted first).
- S2 · security: `tl_core/confidentiality.py` subject part for `qr.ScanCode`.
- S3 · security: a web route whose miss must equal the sign-in-protected 404.
- T02 · dependency: `segno` as the optional extra `labels` of `tl-mod-qr` (already licensed for the awp `pack` extra).

## Security rows (one review at C4, range `p2/ip` base..head)
S2 one-exit resolver, hash-only storage, generator source, no code in any event, error or log; S3 sign-in before
lookup, byte-equal misses, rate limit, headers; S1 contract bounds; T04/T05 cards read under the viewer; T06 walk;
T10 CSRF and origin check; agents refused on every route.

## Risks and escalation triggers
- ADR-0030 is proposed. S1 may be built; nothing merges before it is accepted.
- P2-X4 hooks: S2 declares hooks, so it needs X4 C2 on the trunk and merged into `p2/ip`. S1 does not.
- `tl_web/routers.py` `PAGE_MODULES` is a shared one-line file: only S3 touches it.
- Escalate: any change to the frozen card contract after C1; a miss that cannot be made byte-equal; a piece failing twice.

## Plan check
Pending (`4 PLANCHK docs/tickets/P2-QR/README.md`): over 10 items and a core-interface ADR. S1 may be built while it
runs; no merge and no ticket dispatch before each finding is answered here.

## Fan-out across P2-QR, P2-INSP and P2-PTW
- **Integration branch** `p2/ip`, created from `p2/design-ip` (trunk @d4e92ffc plus these documents). The three
  increment branches start from it and merge back into it; `p2/ip` goes to the trunk after each increment's C4.
- **Merge order of the schema pieces:** QR S1, then INSP S1, then PTW S1. All three touch the same pinned lists
  (`access-words.yaml`, numbering patterns, offline classes, word and module counts) and `generated/**`. They may be
  built at the same time in their own worktrees; each later one merges `p2/ip` in first, re-runs `just gen` and
  `just compat-update`, and re-adds its pin counts.
- **Who resolves conflicts:** generated files and pin counts: the orchestrator regenerates. Anything else: the
  supervisor of the increment merging later (INSP over QR, PTW over both).
- **Cross-increment waits:** the inspection card (INSP T09) and the permit card (PTW T09) need QR C1 and QR T03.
  QR T05 needs P2-I4B on the trunk. Every S2 needs P2-X4 C2 on the trunk. P2-I4B S1 touches the same pins: whichever
  merges second regenerates.
- **Slots:** at most three heavy agents alive. Steady state: one builder piece per increment in turn plus one ticket
  workflow of up to four implementer tickets drawn from all three boards; two gate runs at once.
- **Learnings to hand each supervisor:** L-P1-I7B-9, L-P1-I8-3, L-P2-I1-2, L-P2-I3-2, L-P2-I3-3, L-P2-WEB1-1,
  L-P2-WEB1-2 (QR S3, T10), L-P2-WEB1-3.

## Blocked / Decision
(none yet)

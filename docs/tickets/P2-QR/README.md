# P2-QR — QR codes at the workface: scan codes, status cards, labels

Status: plan check answered (r1b, 2026-11-15; nothing dispatched). 3 pieces, 12 tickets: 7 in the first slice, 5 in the
follow-up slice. **today** marks today's slice (about 10 M tokens across P2-QR, P2-INSP and P2-PTW).
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
   command writes a label file whose QR text is `<base>/web/q/<16 chars>` and contains no key, id or project code.
2. Signed out, `GET /web/q/<code>` and `GET /web/q/<nonsense>` give the same sign-in response. Signed in as a reader who can
   see the IWP, the page shows the state banner, key, "as of" time and lines.
3. Five misses, one answer: unknown, revoked, expired, hidden record, no view word: byte-identical 404 pages.
4. Rotate: the old code is a miss, the new one resolves; `tl qr ls <key>` shows both rows and never a code.
5. Scaffold card (when P2-I4B is on the trunk): a red tag shows the stop banner; else the clause prints `deferred`.
6. An agent token gets the closed guard's 403 on `/web/q/…` and on the code register, before any lookup, so it learns
   nothing about a code; a signed-in person gets the one 404 miss. `tl qr export --format jsonl` rows equal `tl qr ls`.
7. `tl qr resolve` (code from stdin or a prompt, never argv) on an embedded ledger prints the same card text.
8. With P2-INSP and P2-PTW merged: a label for an inspection and for a permit each resolves to its status card.
   Clauses 5 and 8 print `deferred` when the card they need is not merged.

## Checkpoints
C1: S1 merged to `p2/ip` (schema, setting, words, frozen card contract; APPROVALS). C2: S2 and S3 merged (code
service, scan page; hooks follow later, see risks). C3: every ticket merged or abandoned. C4: per-folder gates on touched packages, `gate-pg` on
touched directories, demo on both adapters, tour shots, security review closed.

## Items (first slice)
Tier B = builder piece (`kind: piece`); H = implementer ticket. Sec = a row for the wave's security review.

| ID | Title | Tier | Depends | Sec | Review | Slice |
|---|---|---|---|---|---|---|
| S1 | Schema `schema/modules/qr/` (`qr.ScanCode`, two events), settings `api.public_base_url` (URL shape `<base>/web/q/<code>`), `qr.codes_per_record_max`, three words, module skeleton, optional extra `labels` (`segno`), the frozen contract `tl_core/qr/types.py` and registry | B | `p2/ip` | yes | full | today |
| S2 | Code service and commands as services and handlers with no hook fields: generate, hash, `IssueScanCode` (refused without the base address), `RevokeScanCode`, `RotateScanCode`, `resolve()` with one exit for every miss, `label_fields(target, viewer)`, subject part in `confidentiality.py`, error types that raise core error classes, deps (`fastapi`, `typer`, `mcp`) and stub registrars, test that every chain including `ScanCode` stays within `_HOPS`, the provided test of T01; sentinel + at most 5 mutants | B | S1 | yes | full | later |
| S3 | Scan page `/web/q` and `/web/q/{code}`: sign-in bounce before any lookup (`next` only `/web/q/[A-Z0-9]{16}`), byte-identical miss, per-session and per-address miss counter with one 429, `no-store`, `no-referrer` override in `tl_web/app.py`, code stripped from the access log (`tl_api/main.py`), runbook proxy note, the five-reader walk | B | S2 | yes | full | later |
| T01 | Read views `tl_mod_qr/views.py`: `codes_for_record`, `code_counts`, `export_rows(rows, "csv"\|"jsonl")` | H | S2 | - | full | later |
| T02 | Label renderer `tl_mod_qr/labels.py` (pure; `tag` size only; fixed note without `segno`); ticket `T02-label-renderer.md`, provided test | H | S1 | - | lite | today |
| T03 | Card contract harness `tests/contract/scan_card_harness.py` and its test; ticket `T03-card-contract-harness.md`, provided test | H | S1 | - | full | today |
| T04 | Card `awp.IWP` (`tl_mod_awp/scan_card.py`, entry point) | H | T03 | yes | full | later |
| T06 | API read router (`GET /qr/codes`, `/qr/codes/export`, JSON `GET /qr/resolve/{code}`) in the module package, five-reader walk | H | T01 | yes | full | later |
| T07 | CLI group `tl qr`: `label`, `ls`, `revoke`, `rotate`, `resolve` (stdin or prompt), `export` | H | T01, T02 | - | full | later |
| T11 | Demo `dev/demos/P2-QR.sh` and driver (clauses 1-4, 6-8; 5 prints `deferred` until QR T05) | H | T04, T06, T07 | - | full | later |
| T12 | Tour shots (scan page at phone width for each tone, label) and docs: module README and AGENTS, runbook `docs/runbooks/qr-labels.md`, root `AGENTS.md` row | H | T11 | - | lite | later |

### Follow-up slice (not scheduled; each waits for the first slice to merge and for a fresh plan round)
| ID | Title | Why it waits |
|---|---|---|
| T05 | Card `scaffold.Scaffold` (`tl_mod_scaffold/scan_card.py`, entry point) | Needs P2-I4B on the trunk |
| T08 | Client methods and fakes | Only the terminal action uses them |
| T09 | Terminal `qr_text.py` and the "Print label" action | Behind T08 |
| T10 | Web "Print label" form (CSRF) | Security row; CLI covers printing first |
| - | `tl qr sheet` and the `card` and `sheet` label sizes | The enum keeps all three values (no schema change later); `labels.py` renders `tag` and refuses the others with a fixed text |
| - | Hook declaration of the module (`commands`, `read_routers`, `cli_groups`, one small ticket per module) | Needs P2-X4 C2 merged into `p2/ip` |

## Waves (workflows of at most 3 items; gates name test files, never a whole package)
Path: S1 -> S2 -> {S3, T01} -> {T06, T07} -> T11 -> T12.
| Wave | Runs together | Notes |
|---|---|---|
| 1 | S1 (with INSP S1; PTW S1 after one of them ends) | Alone on shared pins and generated files; at most 2 heavy runs |
| 2 | workflow {T02, T03} | **today**; needs S1 merged; disjoint paths (module `labels.py`, `tests/contract`) |
| 3 | S2 | Writes the provided test of T01 under `provided/` while it builds (F8) |
| 4 | S3 (builder) and workflow {T01, T04} | T04 needs T03 merged |
| 5 | workflow {T06, T07} | Module routes file, CLI file |
| 6 | T11, then T12 | |
At most two heavy test runs on the box at once.

## APPROVALS lines needed before merge (the orchestrator never self-approves; the owner or a delegation does)
Approvers: the owner for ADR-0030, the schema merges and the security lines; the safety lead for nothing here.
- S1 - ADR-0030 accepted (owner), then schema merge `schema/modules/qr/**` (new module, additive).
- S1 - settings `api.public_base_url`, `qr.codes_per_record_max`; access words `qr.view`, `qr.issue`, `qr.revoke`.
- S1 - core interface `tl_core/qr/types.py` and entry-point group `throughline.scan_cards`.
- S1 - dependency: `segno` as the optional extra `labels` of `tl-mod-qr` (S1 declares the extra; T02 only imports it lazily).
- S2 - security: `tl_core/confidentiality.py` subject part for `qr.ScanCode`.
- S3 - security: a web route whose miss must equal the sign-in-protected 404; the miss counter and log filter.

## Security rows (one wave review over `d4e92ffc..<p2/ip head>` with the union of the Sec rows of the three increments)
S2 one-exit resolver, hash-only storage, generator source, no code in any event, error or log, `label_fields`; S3
sign-in before lookup, `next` pattern, byte-equal misses, rate limit, headers, log filter; S1 contract bounds;
T04 card reads under the viewer; T06 walk; agents refused on every route.

## Risks and escalation triggers
- ADR-0030 is proposed. S1 may be built; nothing merges before it is accepted.
- S2 is built without hook fields (F2): services, handlers and error types that raise core error classes (the errors hook
  is DEFERRED). The hook declaration (at most 5 lines) lands as a later small ticket after X4 C2 reaches `p2/ip`.
- Module surfaces that live in the module package (T06 routes, T07 CLI) need `fastapi`, `typer`, `mcp`: S2 adds the
  dependencies and stub registrars and checks there is no `tl-api` to `tl-mod-qr` cycle. A cycle is an escalation.
- `tl_web/routers.py` `PAGE_MODULES` and `tl_web/app.py` are shared: only S3 touches them.
- Escalate: any change to the frozen card contract after C1; a miss that cannot be made byte-equal; a piece failing twice.

## Fan-out across P2-QR, P2-INSP and P2-PTW
- **Integration branch** `p2/ip`, created from `p2/design-ip` (trunk @d4e92ffc plus these documents). The three
  increment branches start from it and merge back into it; `p2/ip` goes to the trunk after each increment's C4.
- **Heavy runs (F3):** at most 2 at once. QR S1 and INSP S1 run first together; PTW S1 starts when one of them ends.
- **Merge order of the schema pieces (F5):** the first S1 with signed APPROVALS merges first (the plan expects QR S1,
  then INSP S1, then PTW S1, but signatures decide). Each later one merges `p2/ip`, re-runs `just gen` and
  `just compat-update`, and re-pins its counts.
- **Shared files and owners (F4):** the same rule covers `SUBJECT_LINKS` in `tl_core/confidentiality.py`, entry points
  in `packages/tl-modules/awp/pyproject.toml`, TUI navigation and palette lines, the MCP allowlist, the seed section
  list and the `AGENTS.md` rows: the increment whose piece merges first owns the file's shape; a later one merges
  `p2/ip` and only appends its own lines (never reorders); the supervisor of the later one resolves the conflict;
  generated files and pin counts are regenerated by the orchestrator. Each increment's last docs ticket adds its
  `AGENTS.md` row after merging `p2/ip`.
- **Cross-increment waits:** the inspection and permit cards (INSP T09, PTW T09) need QR C1 and QR T03. QR T05 needs
  P2-I4B on the trunk. Every hook declaration needs P2-X4 C2 in `p2/ip`. P2-I4B S1 touches the same pins: whichever
  merges second regenerates.
- **Slots:** at most three heavy agents alive; workflows of at most 3 items; two gate runs at once.
- **Learnings to hand each supervisor:** L-P1-I7B-9, L-P1-I8-3, L-P2-I1-2, L-P2-I3-2, L-P2-I3-3, L-P2-WEB1-1,
  L-P2-WEB1-2 (QR S3), L-P2-WEB1-3.
- **Today's slice (F11):** QR S1, INSP S1, PTW S1, QR T02 and T03, INSP T00, PTW T00.

## Blocked / Decision
(none yet)

## Plan check
Answered 2026-11-15 (r1b); the orchestrator accepted every finding.
| F | Sev | Finding | Answer |
|---|---|---|---|
| F1 | HI | HI QR URL must live under `/web` (cookie `Path=/web`, `tl_web/session.py:13`; `tl_api/auth.py:172`; `tl_web/app.py:44-48,131`) | URL is `<base>/web/q/<code>` in ADR-0030, the spec, S1 and this README; `tl_web/app.py` added to S3 paths (no-referrer override); return-to allowed only as `next` matching `/web/q/[A-Z0-9]{16}` |
| F2 | HI | S2 hooks need X4 C2 | S2 built as services and handlers without hook fields; hook declaration is a later small ticket per module; error types raise core classes (errors hook DEFERRED) |
| F3 | HI | Too many heavy runs | At most 2: QR S1 with INSP S1 first, PTW S1 after one ends (fan-out) |
| F4 | HI | Shared files beyond the schema pins | Merge-order and owner rule extended (fan-out); S2 adds the test that chains including `ScanCode` stay within `_HOPS` |
| F5 | MD | Merge order of S1 pieces | First signed S1 merges first; later ones merge `p2/ip`, `just gen`, re-pin |
| F6 | MD | Module-package surfaces need deps | S2 adds `fastapi`, `typer`, `mcp` and stub registrars, checks the cycle |
| F7 | MD | Pure rules inside S2; reviewer tiers | Rules are INSP T00 and PTW T00 (Haiku, full); QR T10 deferred (here: follow-up) |
| F8 | MD | Supervisor writing provided tests | S2 builder writes T01's provided test under `provided/`; T02 and T03 tests exist now (they need only S1 names) |
| F9 | MD | Scope | T05, T08, T09, T10, `tl qr sheet`, card and sheet sizes moved to the follow-up slice |
| F10 | MD | Workflow size | Workflows of 3; path S1, S2, {S3, T01}, {T06, T07}, T11, T12 |
| F11 | MD | Today's slice | Marked above |
| F12 | MD | Label rule, resolve, rate limit | `label_fields` in S2; `tl qr resolve` reads stdin or a prompt; S3 miss counter, one 429, log filter, runbook proxy note |
| F13 | LO | Approvers | As in the APPROVALS list; `segno` line belongs to S1; one wave security review |
| F14 | LO | Demo clause 6; clause 8 | Reworded; clause 8 added; `dev/accept/P2-I2/T06b.py` added to INSP S3 and PTW S4 paths |
Deviation recorded: T03's helper is `tests/contract/scan_card_harness.py` (the plan placed it in the test file) so that
other tests can import it.

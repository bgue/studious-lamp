# ADR-0030 — QR codes at the workface: opaque revocable codes, signed-in scans, status cards by plugin

Status: Proposed
Date: 2026-11-15
Deciders: orchestrator (draft); the owner decides. New core interface (`tl_core/qr/types.py`) and a new platform
setting, so a human gate (§25.5) and an APPROVALS line before the merge.
Brief sections: §7.5 (deep links from printed QR codes), §19.1 (resolvable URIs), §22.9 (mobile UX notes), §9 M3 (IWP
pack). Builds on ADR-0009 (accounts and sessions), ADR-0010 (module records), ADR-0016 (confidentiality).
Spec: `docs/build-spec/specs/qr-workface.md`.

## Context
The owner asked (2026-11-15) for QR codes that give the status of an inspection, a permit, a scaffold tag and an IWP
at the workface. The brief's resolvable URI (`https://{host}/c/{company}/p/{project}/r/{type}/{key}`) names the
company, project, type and key. Printed on a label in the field it tells any passer-by which records exist, and it
cannot be withdrawn once printed. The IWP pack today encodes the bare record key. `api.public_base_url` was planned
(risk T-11) and dropped from P2-I5, so no deployment knows its own public address. Guest links do not exist yet
(Phase 3 I8). The rule "hidden looks exactly like missing" must hold for a scan as for any read.

## Decision

1. **A QR holds one URL, `<api.public_base_url>/q/<code>`, and nothing else.** The code is 80 random bits in 16
   look-alike-free characters. It carries no record data and no id. The server stores only its SHA-256, in a ledgered
   record `qr.ScanCode` (events `ScanCode.Issued`, `ScanCode.Revoked`). The code is shown once, at print; a reprint is
   a new code.
2. **A scan needs a signed-in person.** Without a session, `/q/<anything>` answers with the sign-in page whether or
   not the code exists. No anonymous status page is built. Agent tokens are refused.
3. **One answer for every miss.** Unknown, malformed, revoked, expired, hidden record, missing view word and missing
   provider all return the same 404 page, byte for byte. A missing view word is never a 403 on this route.
4. **Status comes from a plugin per record type.** `tl_core/qr/types.py` defines `ScanCard` and `ScanCardProvider`
   with bounds; modules register providers under the entry-point group `throughline.scan_cards`. A provider reads
   under the viewer's filter and returns `None` for what the viewer cannot see. The contract is frozen once merged.
5. **Codes are revocable and rotatable, and may expire.** Revoke is a controller act; rotate is revoke plus issue.
   A record reaching a final state does not revoke its codes.
6. **The engine is a small module `qr`** (`packages/tl-modules/qr`), declaring its commands, read routes and CLI
   group through the ModuleSpec hooks. The scan page is a page of the web client. The awp module does not run it.
7. **`api.public_base_url` is added as a platform setting.** Issuing a code is refused while it is unset.
8. **Labels never print state**, and print no key or text for a record above the lowest class.
9. **Scans are reads**: not ledgered, the code stripped from access logs, pages sent `no-store` and `no-referrer`.
10. **Offline is not solved here.** With no signal the paper on site rules. A replica can resolve a typed code
    locally. A site server and phone-side caching wait for Phase 3 sync and Phase 5.

## Consequences
- Contracts changed: new `tl_core/qr/types.py` (frozen); new entry-point group `throughline.scan_cards`; new setting
  `api.public_base_url` and `qr.codes_per_record_max`; new access words `qr.view`, `qr.issue`, `qr.revoke`; one part
  added to the subject rule in `tl_core/confidentiality.py`. No existing event, route or setting changes. The brief's
  resolvable URI (§19.1) stays the form for links inside the product; this ADR diverges from "QR codes encoding
  resolvable URIs" (§22.9) for printed labels only, for the reasons in Context.
- Tickets: `docs/tickets/P2-QR/` (S1 schema and contract, S2 code service, S3 scan page, then tickets). One card
  ticket in each of P2-INSP and P2-PTW, and for awp and scaffold in P2-QR.
- Gates affected: schema merge (module `qr`), settings, core interface, security review of the scan route and the
  resolver. The IWP pack's key-text QR is unchanged; moving it to scan codes is later work.
- Every printed label depends on the base address. Changing it needs a redirect or a reprint (runbook).

## Alternatives considered
| Option | Why not |
|---|---|
| Encode the brief's resolvable URI (company, project, type, key) | Leaks what exists to anyone who sees the label; cannot be revoked; a renumbered or re-keyed record breaks the label |
| Encode the record id (ULID) | Still an id that leaks and cannot be revoked; ids also carry a creation time |
| A signed token (HMAC of the record id and an expiry) with no server record | Cannot be revoked one by one; rotation means changing the key for every label; the id is still inside |
| Anonymous scan page showing the state only | A public bearer link to live site safety status; no viewer to filter by; a new unauthenticated surface. Kept as an owner question, default no |
| Store the code itself so labels can be reprinted | Events are permanent; a stored code is a stored credential the moment an anonymous mode is ever added |
| A core service in `tl_core` with commands in `tl_api.commands` | That file is being rewritten by P2-X2 and P2-X4; the owner's rule is that new surfaces come through module hooks |
| A new `ModuleSpec` hook `scan_cards` instead of an entry-point group | Touches `tl_core/modules.py` while P2-X4 is changing it; the readiness checks already prove the entry-point pattern. Can be folded into the hooks later without changing a provider |
| Let the awp pack renderer own QR codes | Ties scaffold, permits and inspections to the awp module |

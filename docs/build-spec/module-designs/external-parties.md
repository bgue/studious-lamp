# External parties: scoped accounts, guest links, portal

Brief §18.11, §8 (ABAC), §17 Q6, Q10, Q17, §21 (feed and thread participation). Plan `09-phase3-plan.md` I8 T01–T03
(accounts with a party scope, guest links, portal page) and the `Viewer.party` ADR at Phase 3 wave 0. Status:
design v0.1. This is a cross-cutting capability, not a module: every module above gains a party column and a
"shared with" view.

## Users and stories
External: subcontractor PM and QC, client representative and witness, third-party inspector (NDE), vendor,
scaffold firm. Internal: document controller or PM who shares, project admin who issues accounts and links.
- As a **subcontractor PM** I sign in and see only my CWPs and IWPs, the NCRs my party is responsible for, the
  correspondence addressed to me and the threads of those records, and I post progress and answers there.
- As a **client representative** I answer an RFI or acknowledge a transmittal from a link in an email, without an
  account, and the answer is ledgered as my party.
- As a **vendor** I upload an MTR to a receipt's slot from a link that expires.
- As a **document controller** I see exactly what a party can see before I share, and I can revoke a link.

## Records and states
| Record | States |
|---|---|
| `Party` (M10, built) | The organisation; external accounts and links bind to it |
| External account (role `external`, bound to one party) | Invited → Active → Suspended; never `controller` or `admin`, never an agent token |
| `GuestLink` | Issued → Opened → Used → Expired; Revoked. Purpose: inspection sign-off, RFI response, MTR upload, transmittal acknowledgement, certificate witness; optional OTP; actor `guest:<party>/<link>` (a reserved source) |
| Sharing | A record is in a party's scope when assigned to it (a typed `party_id` column on CWP, IWP, requisition, NCR, inspection, NDE request, correspondence) or **(proposed)** explicitly shared by a ledgered `Share` record (record, party, by, until), since the link vocabulary takes no new relation |

## Logs and record screens (log standard)
**Internal: Guest link log.** Columns: Number, Purpose, Party, Record, State, Expires, Used by. Panel: identity
`GL-0088 · RFI response · Meridian`; state `Opened · expires 2026-11-05`; summary `P123-RFI-0328 · OTP on · sent to
j.doe@…`; sections Link (purpose, record, what the link may do), Activity (table Time, Action, Address), Timeline.
Actions: Issued or Opened: Revoke, Resend; any: Open record. Issue a link from the record's actions bar
(`Share by link…`, controller or the record's owner).
**Internal: Shared with party.** Per party, the log of records in its scope (Type, Number, Subject, State, Why:
assigned or shared, Since); action Unshare (for explicit shares). The preview answers "what will they see".
**External account in the TUI or web:** the same logs and record screens as everyone, filtered by the party scope;
hidden records are missing, not refused. The actions bar offers only what the party may do (post in the thread,
answer the RFI, record progress, upload to a slot, acknowledge).
**Portal page (web, `web/portal`):** My items (RFIs to answer, NCRs to respond to, inspections to witness,
transmittals to acknowledge, work orders and IWPs of my scope), Uploads, Sign-offs, Correspondence addressed to my
party. It is a thin page over the same read routes; one command per guest flow.
**Tiles (internal):** links expiring this week, items awaiting a party's answer, parties with no activity in 14 days.

## Workflows and approvals
Account invitation by an admin, bound to a party; a party scope on the viewer: records assigned to or shared with the
party plus one `belongs_to` hop (the IWPs of a CWP), their threads, files and feed cards; `restricted` and
`privileged` never; guest links are single-purpose, expiring, optionally OTP, revocable, and run exactly one command
each with the record's current version; activity by a party is ledgered with the party on the actor; posts by
externals are labelled; `threads.external_parties.can_post` gates thread posts; agents of a party hold nothing.

## Links to other modules
Correspondence (parties exist; items to and from a party); M3 (subcontracted CWPs and IWPs, progress by portal or
inbound); M9 (scaffold firm work orders); M5 (NCR responsible party, witness on inspections); M6 (NDE contractor
requests, fabrication shop spools); M7 (certificate witness); M8 (client co-signature on certificates); M4 (vendor
MTR upload); M1 (transmittal acknowledgement); models (guest page with the viewer).

## Integrations
A party with a system uses an inbound endpoint (NDE results, scaffold status, subcontractor progress) instead of or
beside accounts (Q10, P3-Q7). Webhooks to a party's endpoint deliver `thin` payloads for its scope. Mentions
`@party:acme-nde` reach the party's accounts. Email bridge for threads stays off by default.

## Reports
Open items by party and age; guest link audit (issued, used, revoked, by whom); external activity by party; parties
with overdue answers (ties to M10 clocks).

## Confidentiality and roles
A sixth and seventh reader (`external`, `guest`) join the walking tests; the party predicate lives on the one seam
(`tl_core.confidentiality.Viewer.party`) so every route, tool, feed, replica pull and export obeys it; Legal items
and `privileged` records never reach a party; an external account cannot be named on a privileged item; sharing is
a controller act or the record owner's; revoking an account or a link is admin and immediate. External MCP agents do
not exist in v1.

## First increment vs later
First (Phase 3 I8): the viewer party scope ADR and walking readers; role `external` and accounts; guest links with
the four flows; the portal page; party columns on the Phase 2 and 3 records; the HSE and Interface domain files;
the Legal domain file with its exclusions.
Later: party self-service (invite a colleague); client SSO (Q5); PWA for parties (Phase 5); explicit `Share`
records if columns are not enough **(proposed)**; party-level dashboards; external agent identities (not v1).

## Open questions for the owner
P3-Q4 accounts, guest links or both; P3-Q7 NDE contractor; P3-Q10 Legal domain approver and exports; brief Q6
(isolation), Q17 (how subcontractors work). New: is a one-hop scope (CWP → IWPs) enough, or do parties need to see
linked documents and tags too? Does the client get accounts for its whole team or one representative? Which flows
must work by email link alone (no sign-in) in v1?

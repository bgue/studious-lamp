# Module spec: correspondence

Status: accepted for Phase 1. Written by: P1-I5 supervisor. Brief sections: §9 (M10), §7.3, §18.10, §24.
Decisions: ADR-0010 (module record storage), ADR-0013 (document controller), ADR-0016 (confidentiality), ADR-0019 (Technical and Commercial items, the evidence trail). The Technical/RFI and Commercial domains, escalation and the evidence trail (P1-I6) are specified in [technical-commercial.md](technical-commercial.md).

## Purpose
Correspondence is every letter, email, memo and set of minutes the project sends or receives. The module numbers each
item, keeps its original and its files, places it in a thread, starts the response clocks its type calls for, and lists it
in one master register beside the transmittals of document control. A domain file says what a type of letter means
(subtypes, clocks, templates); the General domain and the Document-control domain ship with this increment. Issuing a
letter stores a PDF and records a stub send: nothing leaves the machine (no SMTP in Phase 1).

## Record types
| Type | Table | Purpose | Workflow |
|---|---|---|---|
| `correspondence.Correspondence` | `cur_correspondence_correspondence` (+ `cur_correspondence_clearance`) | One letter, email, memo or minutes; numbered `<project>-COR-nnnn` | `correspondence.correspondence`: Draft, Received, Triaged, Issued, Responded, Closed, Void |
| `correspondence.CorrespondenceThread` | `cur_correspondence_correspondence_thread` | One exchange; numbered `<project>-THR-nnnn`, opened by its first item | open, closed |
| `correspondence.ResponseClock` | `cur_correspondence_response_clock` | A running count to a due date on a project calendar; key `<item number>-Cnn` | running, paused, met, cancelled, expired |
| `correspondence.ContractClause` | `cur_correspondence_contract_clause` | A clause with an optional time bar; key `<contract>/<number>` | active, retired |
| `correspondence.Party` | `cur_correspondence_party` (+ `cur_correspondence_contact_role`) | An organisation, its email domains and its contacts; key is its code | active, retired |

Each record is a row of `cur_core_record` plus its typed table (ADR-0010). The schema is `schema/modules/correspondence/`;
the workflow is `schema/fixtures/workflows/correspondence-correspondence.yaml`, and it has no role guards (who may do what
is the access word of each command, below).

## Events
The full catalogue, with payload samples, is `schema/modules/correspondence/events.yaml` and the generated catalog.

| Event type | Meaning | Projector |
|---|---|---|
| `Correspondence.Defined`, `.Updated`, `.Triaged`, `.Reclassified` | Created, changed, domain confirmed, domain corrected | `correspondence` |
| `Correspondence.ThreadAssigned`, `.Issued`, `.Responded`, `.Superseded` | In a thread, issued with its PDF and stub send, answered, replaced | `correspondence` |
| `Correspondence.ConfidentialityChanged`, `.ClearanceGranted`, `.ClearanceWithdrawn` | The class and the named readers of a privileged item | `correspondence` |
| `CorrespondenceThread.Defined`, `.ItemAdded`, `.StateChanged` | Opened (its first item counts), grown, closed | `thread` |
| `ResponseClock.Started` ... `.Expired` | A clock's whole life; the due date is recomputed from the events by the clock engine | `clock` |
| `ContractClause.Defined`, `.Retired` | Clause register | `clause` |
| `Party.Defined`, `.ContactAdded`, `.ContactEnded`, `.Retired` | Party register; contact positions count from 1 and are never reused | `party` |

## Commands and who may run them
`tl_mod_correspondence.commands.API_COMMANDS` lists 28 commands, each with an access word. `user` is any signed-in person;
`controller` is an admin or a document controller (action `control.command.<Name>`, ADR-0013). An agent never runs a command:
it proposes `ConfirmTriage` (`propose_triage`) and a person accepts.

| Access | Commands |
|---|---|
| user | `ReceiveCorrespondence`, `UpdateCorrespondence`, `DraftCorrespondence`, `ConfirmTriage`, `ReclassifyCorrespondence`, `RecordResponse`, `CloseCorrespondence`, `VoidDraft`, `AssignThread`, `StartClock`, `PauseClock`, `ResumeClock`, `RestartClock`, `MeetClock`, `CancelClock` |
| controller | `IssueCorrespondence`, `VoidCorrespondence` (a received item filed in error), `SupersedeCorrespondence`, `SetCorrespondenceConfidentiality`, `GrantClearance`, `WithdrawClearance`, `SweepClocks`, `RegisterParty`, `AddContact`, `EndContact`, `RetireParty`, `DefineClause`, `RetireClause` |

Email in (`IngestEmail`) is not an API command: a message is up to 10 MiB, a command body 1 MiB. The CLI `tl corr mail ingest`
calls it in process.

## The clock engine
A clock is a pure replay of its events against a versioned calendar (`schema/fixtures/calendars/P123-default@1.yaml`). The
first event records the calendar and version it counted on, so a later calendar edit cannot move a due date that was
already given. `calendar` days count every day; `working` days skip the calendar's weekly rest days and holidays. Each
mutating handler replays the events plus the candidate fact and refuses what the engine refuses (`_check_with`). The
**sweep** (`SweepClocks`, `tl corr clock sweep`, the `F5` screen) records `Warned` for the smallest warning threshold a
running clock has crossed and `Expired` once the day is past; repeating it on one day records nothing twice.
`days_left` and `effective_state` in the reads are computed as of today, so an overdue clock shows `expired` before the sweep
has run.

## Domains
A domain is a file (`schema/fixtures/correspondence/domains/*.yaml`, checked against `schema/modules/correspondence/domain.yaml`
and compiled by `tl_mod_correspondence.domains`). It names subtypes with triage keywords, the clocks a subtype starts on
`receipt` or on `issue`, letter templates, the workflow, the numbering pattern and the default class. Routing roles in a
domain are information for people and the register, never an authorisation (D6b).

| Domain | Subtypes | Clocks |
|---|---|---|
| `general` | letter, memo, minutes, notification | letter: reply expected, 14 calendar days from issue, warnings at 7, 3 and 1 days |
| `document_control` | transmittal, review_return, submittal | submittal: review return due, 10 working days from receipt; a register source lists the I2 transmittals |

The suggestion engine (`suggest.py`) is a pure function of the subject, the body and the domain files: whole-word,
case-insensitive keyword matches, a subject match counts double, a keyword shared by two subtypes counts once for the domain,
ties go to `general` and then to the lowest code. It only proposes.

## Threads
`threading.py` holds the pure rules; `handlers/threads.py` applies them to the readable items. An item joins a thread by,
in order: the item it answers, the Message-ID headers (`In-Reply-To`, `References`), an item number in its text, then its
normalised subject. A match with an item that has no thread opens one for both. A thread the viewer cannot read is never joined.

## Email in
`eml.py` parses an untrusted message with the standard library (`email`, policy default) inside the derivation envelope
(`eml_isolated.py`: a child process with a clock and a memory limit). It is bounded and refuses rather than truncates; it
never renders or fetches HTML; every header that becomes record text goes through `clean_text`. The whole original is kept in
the module-only file slot `message`, each attachment goes through the item's upload guard and file scan into the slot
`attachment`, the party is matched by the sender's address and then by its domain, and a Message-ID already in the register
is refused.

## Confidentiality (ADR-0016)
An item is `internal`, `restricted` or `privileged` (the last names the accounts that may read it). The viewer is a context
variable that defaults to the lowest class, so a path that forgets to set it reads nothing. A clock, a thread, a file or an
event that belongs to a hidden item is hidden with it, including the counter and proposal events that name the item in their
payload (`tl_core.confidentiality`: `hidden_event_ids`, `names_hidden_record`). A hidden item answers exactly as one that was
never numbered. A controller who is not named on a privileged item can name and unname readers by id (the lock-out clause), and `tl corr clearance ls` lists ids and accounts. The sweep reads every clock as the system. Restarting or cancelling a time bar is a controller's act (ADR-0016, D6 refinement). The register export (`tl corr report register`) leaves out everything that is not internal unless a controller
names the class, and writes a leading quote before any cell that a spreadsheet would run as a formula (§18.10).

## Surfaces
| Surface | What |
|---|---|
| API | `GET /projects/{project}/correspondence`, `.../{number}`, `/correspondence-threads[/{number}]`, `/correspondence-suggestion`, clocks, parties, clauses, domains; the commands through `POST /commands/<Name>` |
| MCP | `list_correspondence`, `get_correspondence`, `list_response_clocks`, `list_parties`, `suggest_triage` (reads, action `correspondence.read` open to agents) and `propose_triage` (a proposal) |
| CLI | `tl corr ...` (`docs/runbooks/correspondence.md`) |
| TUI | `F5`: register, triage inbox (`a` accepts the suggestion), response clocks (`s` sweeps) |

## Open questions
- Sending is a stub (`delivery: stub`). A real mail transport, delivery receipts and the portal reply arrive with the
  integration phase; the stored PDF and the `Correspondence.Issued` event already carry what a sender needs.
- The calendar is a committed file per project. Editing a calendar through the product (and the holiday import) is not in this
  increment.

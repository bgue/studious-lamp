# ADR-0029 — Delegation by policy: accept by policy, shadow mode first

Status: Proposed
Date: 2026-11-13
Deciders: orchestrator (draft); owner decides the exit from shadow mode. Core interface, so a human gate (§25.5) and an APPROVALS line before merge.
Brief sections: §11.3, §18.12, §25.5. Refines ADR-0027 decision 7. Builds on ADR-0009, ADR-0016, ADR-0017.

## Context
Today an agent only proposes (`ToolMode = Literal["propose"]`, `proposals/types.py:33`). A person accepts every proposal.
People are then the throughput limit, and the pressure is to bypass the queue (ARCH-CRITIQUE B5).
The owner made accept-by-policy a first-year goal (`docs/build-spec/12-extension-plan.md` §0).
ADR-0027 decision 7 kept it open: `Proposal.Accepted` may later gain a `policy` key, as it gained `edits`. Nothing was reserved.
This ADR settles the design now, so the dispatcher, the command catalog (B3) and the module hooks (A1, P2-X4) are built with it in mind.
It is an ADR only. The build is about 4 points and is listed under later work.

Seams that shape the design:
- `accept_proposal` requires `by` to be a person (`ProposalDeciderError`) and runs the command as `by`, with source `mcp:<agent>` (`services/proposals.py:802`).
- A command gets no more rights through a proposal than its decider holds (ADR-0014).
- A service actor holds only the access declared by its owner, and automation never runs an `admin` command (ADR-0017 decisions 5 and 7).
- `SERVICE_ACTOR_RE` allows only the kinds rule, inbound, enricher and action (`integration/contract.py:54`). A module command also needs the module `user` word on the scope (ADR-0021).
- `Proposal.Failed` is terminal and is written after a rollback, in a fresh unit of work (`proposals/types.py:28-31`).
- An agent holds no project or module scope in its token (`auth/types.py:101-108`). P2-X2 S1 adds the filing check.

## Decision

### 1. A policy is a ledgered record
A policy is a stream of its own, `core.DelegationPolicy`, with a projection `cur_delegation_policy`. It is configuration, not a proposal.

| Field | Meaning |
|---|---|
| `policy_id` | stable id |
| `agent` | one `agent:<username>` account |
| `command_type` | one command name. Names are unique across modules (X4 S1 load check) |
| `scope` | one project (first release) or one module scope (later). Never "all" |
| `bounds` | zero or more `{path, op, value}` on the stored command. `op` is `eq`, `in`, `max` or `min` |
| `daily_cap` | accepts per UTC day for this policy. Required, 1 to 50 (Owner choice 3) |
| `expires_at` | required, at most 90 days after grant. A renewal is a new grant |
| `granted_by`, `confirmed_by` | two different accounts (decision 5) |
| `mode` | `shadow` or `live`. Starts as `shadow` |

Events: `Policy.Granted`, `Policy.Confirmed`, `Policy.Revoked`. No event is edited. A policy takes effect only after `Policy.Confirmed`.
Expiry is computed on read from `expires_at`. No expiry event is written, so no filing transaction writes one.
A change is a revoke and a new grant.

Bounds are checked at grant against the command's own model, which is already in the tree:
- A bound whose path is missing from the model fails. The type of `value` must match the field.
- Scalars only. Arrays and free text are refused. `max` and `min` work on numbers and dates only. A value is at most 200 bytes.
- A bound whose path holds a record id is refused at grant. Policy lists never show a stored id the viewer cannot read; an admin is not clearance (ADR-0016).

### 2. A policy accept is a normal `Proposal.Accepted`
- The event type is unchanged. It gains one optional key, `policy`: the `policy_id`. Old readers ignore it.
- `by` is a service actor `svc:policy-<slug>`. A new kind `policy` joins `SERVICE_ACTOR_RE`. Each policy has one owner and a unique actor name (a unique index, as for the other kinds). The name is reserved from clients (`tl_core.services.reserved`, ADR-0017 decision 4).
- The actor holds account access `user`, plus the module `user` word on the policy scope only. It holds this only while the policy is `live`, confirmed, unexpired, and `delegation.enabled` is on. Otherwise it holds nothing.
- It holds no workflow roles (`actor_access` gives service actors none). A command that needs a workflow role is refused. So a transition is out of reach.
- Source stays `mcp:<agent>`. Causation is the `Proposal.Created` event. Correlation is the proposal id.
- The command runs through the same runner and validation as a person's accept.
- The decider rule in `accept_proposal` ("`by` must be a person") widens for this one actor kind. It must resolve to the live policy of that proposal's agent and command.
- Readers that show `by`: the queue, the feed card, the web client and the B8 stats. Each shows `svc:policy-*` as "policy <policy_id>", with the policy visible only through the filtered read (decision 6). B8 stats count policy accepts apart from people's.
- No data migration. Existing events are untouched.

### 3. Shadow mode first: evaluate at filing, never accept
- The evaluator runs after the filing is committed and after the X2 checks, on each proposal from an agent that has a policy for that command.
- In `shadow` mode it writes `Policy.ShadowEvaluated {policy_id, proposal_id, would_accept, reason_code}`. It never accepts, never changes the proposal, never changes queue order.
- Reason codes, closed: `matched`, `out_of_scope`, `bounds`, `cap`, `expired`, `stopped`, `excluded_command`. There is no `no_policy`: the evaluator runs only when a policy exists.
- In shadow mode nothing is accepted, so `cap` counts would-accepts for the day. `cap` is returned with no count, because a count would reveal accepts of hidden records.
- The record holds ids and codes only. No record text, no field values, no counts.
- `core.DelegationPolicy` events and `Policy.ShadowEvaluated` are hidden on `/events`, `/stream`, the change feed and the feed, fail closed (the `hide_stream_types` pattern, ADR-0009). They are shown only through the filtered read.
- Comparison read: per policy, joins each evaluation with the person's later decision. It reports evaluated, would-accept, accepted, rejected, edited on accept, undecided. It runs through the viewer filter, before counting and before LIMIT.
- Shadow verdicts are hidden from deciders until exit, so they do not shape the decisions (Owner choice 5). Only an admin reads the comparison, and an admin is not clearance.
- `live` is refused at grant until the exit decision (decision 8).

### 4. Evaluation order (live mode, later)
1. The filing is committed first, as today. It carries no policy work and cannot roll back because of one.
2. The policy accept then runs in its own unit of work, and stops at the first failing step.
3. Steps: command not excluded (decision 7); agent not stopped (decision 6); a confirmed, live, unexpired policy matches agent, command and scope; the scope resolves for the agent's viewer; every bound holds; the policy daily cap is not reached; then the command runs as in decision 2.
4. A refusal before the command runs writes `Policy.AcceptSkipped {policy_id, proposal_id, reason_code}`. The proposal stays pending for a person.
5. A refusal by the command itself is `Proposal.Failed` as today: terminal, after rollback, in a fresh unit of work. Owner choice 4 may send it back to pending instead, with a new event.
6. The policy cap counts policy accepts. The agent filing cap (`AGENT_DAILY_PROPOSALS`, proposals created per UTC day) is unchanged and is already checked at submit.

### 5. Who may grant
- An admin grants. A different admin confirms. The same account cannot do both (checked on the ledger).
- If the company has one admin, the second approver may be the owner account (Owner choice 6).
- An agent can never grant, confirm, revoke or edit a policy. Agents cannot hold `admin` (ADR-0009).
- Either admin may revoke alone, at once.
- Grant, confirm and revoke are `admin` commands and are excluded from policy (decision 7).
- Moving to `live` is a new grant with a second approver, refused until the owner's exit decision is recorded.

### 6. Stop switch and scope
The P2-X2 S3 stop switch overrides every policy.
- A stopped agent: reason `stopped`, in shadow and live mode. No policy accept while `Agent.Stopped` has no later `Agent.Resumed`.
- The policy path calls the one stop check X2 S3 exposes. It does not copy it.
- Revoking a policy does not resume an agent. Resuming does not revive a revoked policy.

Scope is resolved through the viewer filter (ADR-0016).
- The evaluator reads the scope and the named records as the agent's viewer, the lowest clearance.
- A scope or record the agent cannot read looks exactly like one that does not exist: same text, same status, same reason code `out_of_scope`.
- Policy lists, the comparison and any count run the filter before counting and before LIMIT. They name no hidden record and count none.
- Every new route, tool or feed that shows policies, evaluations or comparison needs a walking test as five kinds of reader.

### 7. The closed exclusion list
Policy never covers these. The list is closed: a new entry is an ADR. No setting or policy adds or removes one.
1. `admin`: any command whose access is `admin`, or whose name has the word `admin`.
2. `money`: any command that sets, approves, pays, commits or changes an amount, rate, budget, price or currency.
3. `access`: accounts, roles, module roles, agent tokens, clearances, scope grants, and these policies.
4. `schema`: schema package draft, approve, publish and adopt; workflow definition changes.
5. `setting`: `ChangeSetting` (a proposable tool type), so an agent cannot flip `delegation.enabled` or a kill switch.
6. `action`: approval of an action proposal (`ACTION_PROPOSAL_TOOL` needs another person).
7. `external`: anything sent outward: `InvokeAction`, webhooks, transmittal issue, email out.
8. `reserved`: confidentiality class changes, and transitions into locked states. Also commands in `tests/tools/proposable_exclusions.toml` (ADR-0027 decision 5), and access `controller` or `company`.
Rules:
- The shape on `CommandSpec.meta` is `delegation: eligible | excluded:<reason>`, with the reasons `admin`, `money`, `access`, `schema`, `setting`, `action`, `external`, `reserved`. A missing key means excluded.
- Only a command marked `eligible` can be named by a policy. The grant command refuses anything else. The evaluator rechecks at every evaluation.
- X4 S4 fails any command that has a Decimal, currency or amount field and is not marked `money`. It also fails a command with neither a mark nor a reason.

### 8. Exit from shadow mode
The owner decides. No agent and no orchestrator decides.
- Measure, per policy: at least 4 weeks and at least 200 decided proposals, agreement at least 98 percent (Owner choices 1).
- Undecided proposals stay out of the denominator.
- Agreement means: would-accept and accepted without `edits`, or would-not-accept and not accepted.
- Two disagreements are counted apart: would-accept then rejected (the unsafe one), and would-not-accept then accepted (lost throughput). The first must be at most 1 in 100 decided.
- The report is a read. It lists counts, rates and every disagreement by proposal id.
- The owner's decision is an APPROVALS line naming the policies that may go live and the measured rates.
- First live release: one agent, one command type, one project. A second live policy needs its own line.

### 9. Additive only
New events, a new stream, one optional key and one new service-actor kind. No existing event type or field changes. No migration. No change to `Command`, the envelope or `ClientInterface`.
The meaning of `by` on `Proposal.Accepted` widens from "a person" to "a person or a policy actor"; decision 2 names the readers.
Everything is behind `delegation.enabled`, off by default. With it off nothing is evaluated or written.

## Trace table
Dec. = decision above.

| Clause | Carried by | What that piece must hold |
|---|---|---|
| Dec. 6 stop overrides policy | X2 S3 (`Agent.Stopped`, `Agent.Resumed`, the accept check) | One callable stop check. Reason `stopped` |
| Dec. 1, 4 policy keys on command name | X4 S1 `CommandSpec` | Unique names across modules; handler signatures unchanged |
| Dec. 7 exclusion list | X4 S1 `CommandSpec.meta` key `delegation` | Shape `eligible | excluded:<reason>`; missing means excluded. X4 S4 checks money fields and marks |
| Dec. 1 bounds | B3 command catalog | Field list taken from the command model |
| Dec. 3 reason codes, Dec. 4 step 3 | B3 catalog | Access word, record types and proposable flag from one source |
| Dec. 3 comparison, undo of a wrong accept | B7 compensation read | `meta.compensated_by`. Lists accepts with `policy` set, by `mcp:<agent>` in a window, with the compensating command. No automatic rollback |
| Dec. 2 generic path | B2 `propose_command` (ADR-0027 decision 4) | Policy applies to what it files, same closed row list |
| Dec. 6 viewer filter | ADR-0016, X2 T04 walk | Five-reader walk over every new read |

## Consequences
- Contracts changed: none now. Later: optional `policy` key on `Proposal.Accepted`; stream `core.DelegationPolicy` (3 events); `Policy.ShadowEvaluated`; `Policy.AcceptSkipped`; service-actor kind `policy`; decider rule; setting `delegation.enabled`. Each needs `schema/**` approval and an APPROVALS line in its build.
- Tickets re-issued: none yet. There is no X2 S3 piece spec in the tree (`docs/tickets/P2-X2` does not exist), so these are must-holds for the specs to come: X2 S3 exposes one callable stop check; X4 S1 carries the `delegation` key shape; X4 S4 adds the delegation class check. The X4 plan is re-read against this ADR at X3 C4.
- Gates affected: this ADR (owner, APPROVALS line); the later schema merge; the build's security review; the owner's exit decision.
- Out of scope: the build; any live accept; the dispatcher.
- Risks: a loose bound lets a wrong accept through. Mitigations: closed list, cap, expiry, stop switch, shadow comparison, owner gate.

## Owner choices (pending)
| # | Question | Recommendation | Owner answer |
|---|---|---|---|
| 1 | Exit measure | Per policy: at least 4 weeks, at least 200 decided proposals, at least 98 percent agreement, undecided excluded; would-accept-then-rejected at most 1 in 100 | |
| 2 | First-release scope | Project scope only; module scope later | |
| 3 | Cap and expiry | `daily_cap` ceiling 50; max expiry stays 90 days | |
| 4 | Live command refusal | Back to pending with a new event, not terminal `failed`, so a person still decides | |
| 5 | Shadow verdicts | Hidden from deciders until exit | |
| 6 | Second approver | May be the owner account when the company has one admin | |

## Alternatives considered
| Option | Why not |
|---|---|
| Agents write directly in a `write` mode | Skips the queue and the access check. Refused by ADR-0027 decision 7 |
| A policy accept runs as the granting admin | Spends one admin's rights on many unseen acts |
| A policy accept as a new event type | Readers, feed and webhooks need a second path for one act |
| Skip shadow mode, go live with caps | No measured evidence for the owner |
| One admin may grant | One account could widen what agents do alone |
| Open exclusion list, by setting | The list is the safety property; a setting changes without review |
| Bounds as expressions | Code in the ledger, which the plan forbids |

## Plan check
4 PLANCHK docs/adr/0029-delegation-by-policy-shadow-first.md
| F1 HI Dec.2 actor: the policy service actor cannot work as written. `SERVICE_ACTOR_RE` allows only rule, inbound, enricher and action (`integration/contract.py:54`). `actor_access` gives an unknown `svc:` name nothing. A module command also needs `by` to hold the module word on the scope (`require_command_access`, ADR-0021, `proposals.py:836-840`). Service actors hold no workflow roles (`actor_access.py:91-96`) -> add the `policy` kind with one owner and a unique name, reserved from clients. Holds account `user` plus the module `user` word on the policy scope only. Only while the policy is live, confirmed, unexpired and `delegation.enabled` is on. No workflow roles, and say so.
| F2 HI Dec.2/4 failure path: `Proposal.Failed` sets the terminal status `failed`, after a rollback, in a fresh unit of work (`types.py:28-31`, `proposals.py:976`). That contradicts "stays pending" and "runs in the filing transaction". -> commit the filing first, then run the policy accept in its own unit of work. A refusal before the command runs is a new `Policy.AcceptSkipped{reason_code}` and the proposal stays pending. A command refusal is `Proposal.Failed` as today (owner picks). Delete "does not fall back to a person".
| F3 HI Dec.7/trace X4 meta: the reserved key only allows `excluded` and is "empty by default", and "unclassified means excluded". So nothing can ever be eligible. Money also cannot be judged "by declared name and access word". -> define `delegation: eligible | excluded:<reason>`, with reasons admin, money, access, schema, action, external, reserved. Missing key means excluded. X4 S4 fails any command that has a Decimal, currency or amount field and is not marked `money`. X4 S1 needs this shape before it starts.
| F4 MD Dec.7 list is incomplete. `ChangeSetting` is a proposable tool type (`types.py:35-36`), so an agent could flip `delegation.enabled` or a kill switch. Also missing: approvals of action proposals (`ACTION_PROPOSAL_TOOL` needs another person, `proposals.py:846`), outbound sends (InvokeAction, webhooks, transmittal issue, email out), confidentiality class changes (the list only names clearances), and transitions into locked states -> add these five entries to the closed list.
| F5 MD Dec.1 bounds: -> a bound whose path is missing fails. Check each path and type at grant against the command model, which is already in the tree (no need to wait for B3). Scalars only: arrays and free text are refused, and `max`/`min` work on numbers and dates only. Cap the size of values. A value that is a record id is refused at grant or shown through the viewer filter on policy lists (an admin is not clearance). Hidden ids would leak through policy lists today.
| F6 MD Dec.3/6 hidden equals missing: the stream of `Policy.ShadowEvaluated` and its hiding on /events, /stream and the feed are not stated -> hide the `core.DelegationPolicy` events fail-closed (`hide_stream_types` pattern) and show them only through the filtered read. `cap` has no meaning in shadow mode because nothing is accepted: count would-accepts instead. `cap` also reveals accepts of hidden records: return `cap` without any count. `no_policy` can never occur, because the evaluator only runs when a policy exists: drop it or define it.
| F7 MD Dec.8 exit: "no would-have-been-wrong case" contradicts "counts against the rate". It is unclear whether 200 means per policy or in total. The money clause means nothing, since money is excluded anyway. -> per-policy minimum. Undecided proposals stay out of the denominator. Count would-accept-then-rejected separately from would-reject-then-accepted. Hide shadow verdicts from deciders while they decide, or the agreement is contaminated.
| F8 MD Dec.4 step 6: the existing agent cap counts proposals created per UTC day (`types.py:99-101`), not accepts -> "the policy cap counts policy accepts; the agent filing cap is unchanged and already checked at submit".
| F9 MD Trace/Consequences: "Tickets re-issued: none" is wrong. There is no X2 S3 piece spec yet (no `docs/tickets/P2-X2`), so O1 cites a file that does not exist. -> list as must-holds: X2 S3 exposes one callable stop check; X4 S1 carries the F3 key shape; X4 S4 adds the delegation class check. The B3 row should say "field list from the command model". Re-read at X3 C4.
| F10 LO Dec.9 additive claim: `Proposal.Accepted.by` was documented as a person (ADR-0027, `proposals.py:816`), so its meaning widens -> name the readers (queue, feed, web, B8 stats) and how they show `svc:policy-*`. `Policy.Expired` "written when first seen" writes in an agent's filing transaction -> compute expiry on read, or write it from a job.
| 30

### Answers

F1 done: decision 2 adds service-actor kind `policy`, unique name, reserved from clients; holds `user` plus module `user` word on scope, only while live, confirmed, unexpired and enabled; no workflow roles, stated
F2 done: decision 4 commits the filing first and runs the accept in its own unit of work; `Policy.AcceptSkipped` keeps the proposal pending; command refusal is `Proposal.Failed` (Owner choice 4); fallback sentence deleted
F3 done: decision 7 defines `delegation: eligible | excluded:<reason>`, missing means excluded, X4 S4 money-field check, trace row updated; also added reasons setting (F4) in the list
F4 done: decision 7 adds setting, action approval, external sends, confidentiality class changes and locked-state transitions
F5 done: decision 1 checks path and type at grant against the command model, scalars only, numbers and dates for max/min, 200-byte values, record-id bounds refused, lists filtered
F6 done: decision 3 hides policy and evaluation events fail closed; `cap` counts would-accepts and shows no count; `no_policy` dropped
F7 done: decision 8 per-policy minimum, undecided out of the denominator, two disagreements counted apart, money clause removed, verdicts hidden from deciders (Owner choice 5)
F8 done: decision 4 step 6 states the policy cap counts policy accepts and the filing cap is unchanged
F9 done: Consequences lists the three must-holds and says no X2 S3 spec exists yet; B3 row says field list from the command model; re-read at X3 C4
F10 done: decision 2 names queue, feed, web and B8 stats and how they show the actor; expiry computed on read, `Policy.Expired` removed

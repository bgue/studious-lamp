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
- An agent holds no project or module scope in its token (`auth/types.py:101-108`). P2-X2 S1 adds the filing check.

## Decision

### 1. A policy is a ledgered record
A policy is a stream of its own, `core.DelegationPolicy`, with a projection `cur_delegation_policy`. It is configuration, not a proposal.
Fields:

| Field | Meaning |
|---|---|
| `policy_id` | stable id |
| `agent` | one `agent:<username>` account |
| `command_type` | one command name. Names are unique across modules (X4 S1 load check) |
| `scope` | one project or one module scope. Never "all" |
| `bounds` | zero or more field bounds, each `{path, op, value}` on the stored command. `op` is `eq`, `in`, `max` or `min`. No code, no expressions |
| `daily_cap` | accepts per UTC day for this policy. Required, at least 1 |
| `expires_at` | required. At most 90 days after grant. A renewal is a new grant |
| `granted_by`, `confirmed_by` | two different admin accounts (decision 5) |
| `mode` | `shadow` or `live`. Starts as `shadow` |

Events: `Policy.Granted`, `Policy.Confirmed`, `Policy.Revoked`, `Policy.Expired` (written when first seen past expiry). No event is edited.
A policy takes effect only after `Policy.Confirmed`. A change to a policy is a revoke and a new grant.
A policy that matches nothing in bounds does nothing. Bounds only narrow; there is no way to widen a command.

### 2. A policy accept is a normal `Proposal.Accepted`
- The event type is unchanged. It gains one optional key, `policy`: the `policy_id`. Old readers ignore it. Events without it are as before.
- `by` is the service actor `svc:policy-<policy_id>`. It is not a person, and it is not the granting admin.
  The decider rule is relaxed for this actor only: it must resolve to a live, confirmed, unexpired, `live` policy of that proposal's agent and command.
- The actor holds access `user` and nothing above it (ADR-0017 decision 7 pattern). A command that needs `controller` or `admin` access is refused by the command's own check.
- Source stays `mcp:<agent>`. Causation is the `Proposal.Created` event. Correlation is the proposal id, as for a person's accept.
- The command runs through the same runner and the same validation as a person's accept. Nothing is skipped.
- A refusal records `Proposal.Failed` as today. A failed policy accept does not fall back to a person; the proposal stays in the queue as pending (see decision 4, step 6).
- No data migration. Existing proposals and events are untouched.

### 3. Shadow mode first: evaluate at filing, never accept
- At filing, after the X2 checks, the evaluator runs on every proposal from an agent that has a `shadow` or `live` policy for that command.
- In `shadow` mode the evaluator writes a record, `Policy.ShadowEvaluated`, with `{policy_id, proposal_id, would_accept: bool, reason_code}`. It never accepts, never changes the proposal, never changes its order in the queue.
- Reason codes are a closed list: `matched`, `no_policy`, `out_of_scope`, `bounds`, `cap`, `expired`, `stopped`, `excluded_command`.
- The record holds ids and codes only. It holds no record text, no field values, no counts of hidden things.
- Comparison: a read joins `Policy.ShadowEvaluated` with the person's later `Proposal.Accepted` or `Proposal.Rejected`.
  It reports per policy: evaluated, would-accept, person accepted, person rejected, edited on accept, failed. Agreement means `would_accept` and the person accepted without `edits`, or `not would_accept` and the person did not accept.
  The read runs through the viewer filter (decision 6).
- Shadow mode works without any live path. In the first build, the `live` mode is refused at grant time (decision 8).

### 4. Evaluation order (live mode, later)
A live evaluation runs at filing, in the filing transaction, and stops at the first failure. Any failure leaves the proposal pending for a person.
1. The command is not on the exclusion list (decision 7).
2. The agent is not stopped (decision 6). A stopped agent is never accepted.
3. A confirmed, unexpired policy matches agent, command type and scope.
4. The scope resolves for the policy's viewer (decision 6).
5. Every bound holds on the stored command.
6. The policy daily cap and the existing agent daily cap are not reached. The cap counts accepts, not filings.
7. The command runs as in decision 2.

### 5. Who may grant
- A grant needs an admin to propose it and a different admin to confirm it. The same account cannot do both (checked on the ledger, not on a form).
- An agent can never grant, confirm, revoke or edit a policy. Agents cannot hold `admin` (ADR-0009).
- Either admin may revoke alone, at once. Revoking is the safe direction.
- Grant, confirm and revoke are `admin` commands. They are themselves excluded from policy (decision 7).
- Moving a policy from `shadow` to `live` is a new grant with a second admin, and it is refused until the owner's exit decision is recorded (decision 8).

### 6. Stop switch and scope
The P2-X2 S3 stop switch overrides every policy.
- A stopped agent: the evaluator returns `stopped`, in shadow and in live mode. Policy accept is refused while `Agent.Stopped` has no later `Agent.Resumed`.
- The stop check is the same check X2 S3 puts at accept. The policy path calls it; it does not copy it.
- Revoking or expiring a policy does not resume an agent. Resuming an agent does not revive a revoked policy.

Scope is resolved through the viewer filter (ADR-0016).
- The evaluator reads the scope and the records the command names as the agent's viewer: the lowest clearance, as every agent read does.
- A scope or record the agent cannot read looks exactly like one that does not exist. The refusal text, the status and the reason code are the same: `out_of_scope`.
- The shadow comparison read, a policy list and any count run the filter before counting and before LIMIT. They name no hidden record and count none.
- A policy is not clearance. An admin who grants a policy gains no read on the records it covers (ADR-0016).
- Every new route, tool or feed that shows policies, evaluations or comparison needs a walking test as five kinds of reader.

### 7. The closed exclusion list
Policy never covers these. The list is closed: a new entry is an ADR, and nothing is added by a setting or a policy.
1. Any command whose access word is `admin`, or whose name has the word `admin`.
2. Money: any command that sets, approves, pays, commits or changes an amount, rate, budget, price or currency value.
3. Access: accounts, roles, module roles, agent tokens, clearances, scope grants, and these policies themselves.
4. Schema publication: schema package draft, approve, publish and adopt; locked states and transitions; workflow definition changes.
Also excluded, as already decided: commands in `tests/tools/proposable_exclusions.toml` (ADR-0027 decision 5), and commands with access `controller` or `company`.
A command is on the list by its declared name and access word, not by what an agent says it does. The grant command refuses a policy that names one. The evaluator rechecks at every evaluation.
A command that cannot be classified is excluded. The conformance test (X4 S4) fails a module command that has neither a class nor a reason.

### 8. Exit from shadow mode
Shadow mode is the only mode until the owner decides otherwise. No agent decides, and no orchestrator decides.
- Measure: agreement rate per policy (decision 3), over at least 4 weeks and at least 200 evaluated proposals, with no policy-accept-would-have-been-wrong case: a would-accept that a person rejected or edited counts against the rate.
- The report is a read, not a dashboard. It lists, per policy, the counts and the rate, and every disagreement by proposal id.
- The owner sets the threshold for the rate. No default is baked in. The recommended start is 98 percent with zero disagreements on bounded money-adjacent fields, which are excluded anyway.
- The owner's decision is an APPROVALS line naming the policies that may go live and the rate that was measured.
- The first live release is one agent, one command type, one project. A second live policy needs its own line.
- Until then a grant with `mode: live` is refused with a fixed text.

### 9. Additive only
New events and an optional key. No existing event type changes. No existing field changes meaning. No migration. No change to `Command`, the envelope or `ClientInterface`.
Everything is behind a setting that is off by default (`delegation.enabled`). With it off, nothing is evaluated and nothing is written.

## Trace table
Each clause (Dec. = decision above) maps to the piece that carries it, so the later builds need no change of contract.

| Clause | Carried by | What that piece must hold |
|---|---|---|
| Dec. 6 stop overrides policy | X2 S3 (`Agent.Stopped`, `Agent.Resumed`, the accept check) | One callable stop check the policy path can call. Evaluator reason `stopped` |
| Dec. 1, dec. 4 policy keys on command name | X4 S1, `CommandSpec` | Command names unique across modules (load refuses a clash). Handler signatures unchanged |
| Dec. 7 exclusion list | X4 S1 `CommandSpec.meta`, key `delegation` | Optional value `excluded` plus a reason. Empty by default. Unclassified means excluded. X4 S4 enforces row-or-exclusion |
| Dec. 1 bounds on `path` | B3 command catalog | Per-command field list, so a grant can check that a bound names a real field |
| Dec. 3 shadow `reason_code`, dec. 4 step 1 | B3 catalog | Access word, record types, proposable flag read from one source |
| Dec. 3 comparison, undo of a wrong accept | B7 compensation read | `meta.compensated_by`. The read lists accepts with `policy` set in a window by `mcp:<agent>`, with the compensating command for each. No automatic rollback |
| Dec. 2 generic path | B2 `propose_command` (ADR-0027 decision 4) | Policy applies to the proposals it files, with the same closed row list |
| Dec. 6 viewer filter | ADR-0016, X2 T04 walk | Five-reader walk over every new read |

## Consequences
- Contracts changed: none now. Later: one optional key `policy` on `Proposal.Accepted`; the stream `core.DelegationPolicy` with four events; `Policy.ShadowEvaluated`; the decider rule for `svc:policy-*`; the setting `delegation.enabled`. Each needs `schema/**` approval and an APPROVALS line in its build.
- Tickets re-issued: none. X4 S1 reads decision 1 and 7: the `meta` mapping stays optional, and `delegation` is one reserved key in it. The X4 plan is re-read against this ADR (X3 checkpoint C4).
- Gates affected: this ADR (owner, APPROVALS line); the later schema merge; the security review of the build; the owner's exit decision (decision 8).
- Out of scope: the build; any live accept; the dispatcher; the exclusion of a command by a policy owner.
- Risks: a bound that is too loose lets a wrong accept through. Mitigations are the closed list, the cap, the expiry, the stop switch, the shadow comparison and the owner gate.

## Alternatives considered
| Option | Why not |
|---|---|
| Agents write directly in a `write` mode | Skips the queue and the person's access check. Refused by ADR-0027 decision 7 |
| A policy accept runs as the granting admin | Spends one admin's rights on many unseen acts, and breaks "no more rights than the decider holds" |
| A policy accept as a new event type | Readers, the feed and webhooks would need a second path for one act. The `policy` key is additive |
| Skip shadow mode, go live with caps | No measured evidence; the owner has nothing to decide on |
| One admin may grant | A single account could widen what agents do alone. Two admins is the existing pattern for schema packages |
| Open exclusion list, by setting | The list is the safety property. A setting can be changed without review |
| Policy bounds as expressions | Code in the ledger. Rejected by the plan rule: nothing loads code from the ledger |

## Plan check

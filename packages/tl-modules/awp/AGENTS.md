# AGENTS.md — tl-mod-awp

Read the root `AGENTS.md` first. These rules add to it.

- The tables `cur_awp_*` are generated from `schema/modules/awp/` and written only by the projectors. A record is made with `create_module_record` (ADR-0010).
- Every command checks `require_project`, `require_visible` on each id it is given, and its access word (`schema/settings/access-words.yaml`). Rule messages are fixed text, never a cell of the input.
- Links from a WBS node to its cost codes are written and retracted by the module (`by_module=True`, source `rule`); a person never touches them. Core feed code silences the eight `feed_policy: none` events (`tl_core/feed/cards.py`).
- `rollup.request()` queues; the run is the rollup job. Spec: `docs/build-spec/specs/m3-wbs-cwp.md`.
- Keys of typed records are namespaced per type (`awp.wbs@`, `awp.cwa@`, `awp.ewp@`, `awp.pwp@`; `names.py` `KEY_PREFIX`). Never build a key of another module's type or without its prefix.
- A read of a record, its history or its links goes through the viewer's filter (`tl_core.confidentiality`, ADR-0016). A hidden record answers as one that does not exist; a test that widens the viewer default is wrong.
- Events are immutable. Never delete or rewrite an `awp` event; a correction is a new event.
- Reinstate, do not delete. A retired WBS node comes back by `ReinstateWbsNode` (`WBSNode.Reinstated`) or by a reload under the same parent. No awp command removes a node, a CWA or a CWP row.
- The MCP tool `propose_cwp` only files a proposal. No agent tool may create, revise or void an awp record.
- IWP sign-off and issue are gated by the record hash: `SignOffIwp` and `IssueIwp` take the hash from `iwp hash`, and a stale hash is refused. Sign-off needs two distinct signers, each holding a role in `awp.release.signoff_roles`; do not widen that setting to get a sign-off through.
- `IWP.Ready` and `IWP.ReadinessEvaluated` are written only by the readiness job (`ready:<iwp>`, `tl_mod_awp/readiness/`), never by a command or a projector. The readiness projector writes `cur_awp_readiness` from those events only.
- The nine readiness checks are read-only: a check reads nothing it does not need, uses no write, and answers one fixed detail text. `n_a` counts as passing (D9). A new check is registered through the entry-point group `throughline.readiness_checks`.
- Constraints are core records (ADR-0024). awp holds no `awp.constraint.*` word; a constraint is raised, assigned, cleared or withdrawn only through the core commands (`core.constraint.edit`), and read through `core.constraint.view`.
- The MCP IWP tools (`tl_mcp/iwp_tools.py`) are four reads and `propose_iwp_scope`. The proposal is not a write. Agents hold no constraint tool (D37).
- Weekly plan, progress and the work pack are people's words (`awp.week.*`, `awp.progress.record`, `awp.iwp.edit`). An agent proposes only (`propose_progress`, `propose_week_commitment`); an agent is refused `CloseWeek` and `ClearConstraint` with `agent_must_propose`.
- Handlers never read `intent` (ADR-0025).
- A week closes once and is final: no command reopens it, and an outcome changes only while the week is `Committed`.
- Progress figures keep the rules-of-credit edition in force when they were recorded. Never recompute a stored figure under a later edition.
- The hold rule (`readiness/hold_rule.py`) reads `Constraint.Raised` only, moves an Issued IWP only, and never raises a constraint. It runs in `tl awp worker`, which needs `awp.worker.run`.
- A viewer's roll-up, export and KPI tiles are computed from the records the viewer may open; the stored `cur_awp_rollup` totals are not read for a viewer.
- Every record value in the work pack goes through `_e` before it reaches the template; the template holds no record value and no record id.

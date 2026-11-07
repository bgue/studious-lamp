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

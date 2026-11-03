# AGENTS.md — tl-mod-awp

Read the root `AGENTS.md` first. These rules add to it.

- The tables `cur_awp_*` are generated from `schema/modules/awp/` and written only by the projectors. A record is made with `create_module_record` (ADR-0010).
- Every command checks `require_project`, `require_visible` on each id it is given, and its access word (`schema/settings/access-words.yaml`). Rule messages are fixed text, never a cell of the input.
- Links from a WBS node to its cost codes are written and retracted by the module (`by_module=True`, source `rule`); a person never touches them. Core feed code silences the eight `feed_policy: none` events (`tl_core/feed/cards.py`).
- `rollup.request()` queues; the run is the rollup job. Spec: `docs/build-spec/specs/m3-wbs-cwp.md`.

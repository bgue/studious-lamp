# Delegated approvals

Approvals the orchestrator gave under the KICKOFF delegation, for human review. Format: `throughline-docs` skill §5.

- 2026-10-09 · P0-I1-T02 · schema merge `schema/core/{annotations,record,ledger,core}.yaml` (RecordEnvelope, Record, Event, ConformanceStatus) ·
  within §5.1 event model and §6.2 envelope, and the P0-I1 plan · approved by orchestrator under KICKOFF delegation · commit 6e3827b on p0/i1
- 2026-10-09 · P0-I2-T07 · schema merge `schema/core/psets.yaml` (pset value storage and `cur_pset_values` table) · within §6.3 layers and §5.4 `cur_pset_values`, and the P0-I2 plan · approved by orchestrator under KICKOFF delegation · commit 27e2e54 on p0/i2a
- 2026-10-09 · P0-I2-T07 · schema merge `schema/core/annotations.yaml` (platform annotation docs) and `schema/core/core.yaml` (one import) · entailed by psets.yaml; the annotations are the platform rules named in §27.3 (`tl:enforcement`, `tl:value_list_policy`, `tl:materialize`) · approved by orchestrator under KICKOFF delegation · commit 27e2e54 on p0/i2a
- 2026-10-09 · P0-I2-T02 · schema merge `schema/fixtures/co.acme.engineering@3.2.0.yaml`, `x.P123@1.4.0.yaml`, `prj.P123@1.0.0.yaml` · the §6.3 worked example (company standard pset, project extension, project custom pset) · approved by orchestrator under KICKOFF delegation · commit 744a6c5 on p0/i2a
- 2026-10-09 · P0-I2 WS-A · dependency `pyyaml` added to tl-schema · YAML schema packages (§27.2, 03 §2 toolchain implies YAML parsing for LinkML packages) · approved by orchestrator under KICKOFF delegation · p0/i2a

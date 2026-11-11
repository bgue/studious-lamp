# tl-mod-quality

The quality module (M5), first slice: one record type, `quality.PunchItem` (`P123-PUN-0001`).

- Schema: `schema/modules/quality/`; workflow `schema/fixtures/workflows/quality-punch-item.yaml`.
- Module spec: `tl_mod_quality.module:spec` (entry point `throughline.modules`).
- Commands arrive with P2-PUNCH S2; `PUNCH_COMMANDS` is empty until then.

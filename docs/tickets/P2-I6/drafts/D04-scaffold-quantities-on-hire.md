# D04 — Requisitions/WO report: scaffold quantities on hire

Status: draft
Source: P2-I6-T03 audit, row 14 (brief §12, Requisitions/WO). Status BLOCKED-BY I4-B.

Goal: add the §12 report "scaffold quantities on hire" with the CLI and route shape used by the
other reports.

What the report shows: the scaffold quantities currently on hire, by type and by hire period.

Existing view or command: none. `tl req ls --kind scaffold` lists requests only; no quantity
on hire is recorded yet.

Dependency: I4-B (scaffold module: hire records and quantities). Shares the module with D03.

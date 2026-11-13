# D03 — Requisitions/WO report: scaffold register

Status: draft
Source: P2-I6-T03 audit, row 13 (brief §12, Requisitions/WO). Status BLOCKED-BY I4-B.

Goal: add the §12 report "scaffold register" (status, tag colour, inspection due) as a report
name on the requisitions side, with the same CLI and route shape as the other reports.

What the report shows: one row per scaffold: tag, status, tag colour and the next inspection due date.

Existing view or command: none. `tl req raise-scaffold` raises a request only; `tl req ls --kind
scaffold` lists requests, not a register.

Dependency: I4-B (scaffold module: scaffold records, tag colour, inspection dates).

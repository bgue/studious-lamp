# D05 — Requisitions/WO report: labour requisition forecast by craft and week

Status: draft
Source: P2-I6-T03 audit, row 15 (brief §12, Requisitions/WO). Status GAP.

Goal: add the §12 report "labor requisition forecast by craft/week" to the requisitions reports,
on the CLI and the API.

What the report shows: labour headcount by craft and by week, from the labour requisitions'
start and end dates and headcount.

Existing view or command: none. `tl req ls --kind labor` lists requisitions and does not forecast.
The forecast is deferred (DEFERRED.md, I4-A trimmed parts, owner roadmap row 3c).

Dependency: roadmap 3c (the forecast was trimmed from I4-A). No module blocks it.

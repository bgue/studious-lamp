# D01 — AWP report: backlog of ready IWPs (weeks of backlog)

Status: draft
Source: P2-I6-T03 audit, row 4 (brief §12, AWP/WBS)

Goal: add the §12 report "backlog of ready IWPs" as a named `tl awp report` and as an
`/projects/{project}/awp/reports/{name}` value.

What the report shows: for each project, the IWPs that are ready (readiness passed, no blocking
constraint) and how many weeks of work they hold, from the planned weekly capacity.

Existing view or command: none. `tl awp report` has no backlog name (CWP, IWP, constraint and KPI
names only). `/projects/{project}/awp/look-ahead` lists weeks, not the backlog.

Dependency: P2-I5 readiness and weekly capacity (on the trunk). No external module.

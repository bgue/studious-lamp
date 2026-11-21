# Agent skills

Skills for agents that work with X-ray data outside the viewer (Claude Code, the Claude Agent SDK, or any agent that reads
`SKILL.md` skills). Install one by copying its folder into `.claude/skills/` of a project (or `~/.claude/skills/`).

| Skill | What it does |
| --- | --- |
| [ifc-4d-schedule](ifc-4d-schedule/SKILL.md) | Writes accepted 4D links (schedule activities, the elements they build or remove, dates, logic, `Xray_4D` location / trade / activity IDs) into an IFC, through an IFC MCP server or with IfcOpenShell (`scripts/apply_links.py`, checked by `scripts/verify.py`). Tested on the FZK-Haus sample: 21 tasks, 15 links, 19 logic links, 82 elements, re-runs give the same file. |

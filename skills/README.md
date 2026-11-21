# Agent skills

Skills for agents that work with X-ray data outside the viewer (Claude Code, the Claude Agent SDK, or any agent that reads
`SKILL.md` skills). Install one by copying its folder into `.claude/skills/` of a project (or `~/.claude/skills/`).

| Skill | What it does |
| --- | --- |
| [ifc-4d-schedule](ifc-4d-schedule/SKILL.md) | Reads a P6 XER and an IFC itself, links activities to elements (rules from a 4D configuration plus the agent's own proposals for review), writes the schedule into a copy of the IFC (IfcWorkSchedule, IfcTask with dates, task-to-element assignments, logic, `Xray_4D`) and link status into a copy of the XER, and writes animation scripts that play any part of the build in schedule order (checked with the viewer's own compiler). IFC MCP or IfcOpenShell. `scripts/selftest.sh` runs it all on the FZK-Haus sample. |

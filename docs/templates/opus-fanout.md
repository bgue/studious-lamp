# Fanout plan — <phase>-<increment or scope>

Status: draft | active | integrated
Orchestrator session: <date>
Brief sections: §…

## Objective
One paragraph. What is true when this fanout is integrated.

## Exit criteria
- [ ] …

## Workstreams

| WS | Name | Supervisor | Provides (interfaces) | Consumes | Branch |
|---|---|---|---|---|---|
| A | | | | | `p<n>/i<m>/ws-a` |

## Shared contracts (verbatim, committed before fanout)
```python
# path in repo
```

## Merge order and conflict owner
1. WS-A → integration branch
2. …
Conflicts resolved by: <supervisor of the later-merging workstream>, merge commits only.

## Human gates
| Gate | Approver | Where recorded |
|---|---|---|

## Risks and escalation triggers
- …

## Decisions log
| Date | Raised by | Question | Decision | ADR |
|---|---|---|---|---|

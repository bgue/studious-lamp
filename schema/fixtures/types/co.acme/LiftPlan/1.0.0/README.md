# co.acme.LiftPlan 1.0.0

Example object-backed extension record type (brief 31): a planned crane lift.

| File | Purpose |
|---|---|
| `type.yaml` | LinkML class `LiftPlan` (`is_a ExtensionRecord`); index fields are the slots with `tl:index` |
| `form.yaml` | Layout hints for the generated form and grid |
| `workflow.yaml` | Draft, Approved, Executed, Cancelled |
| `settings.yaml` | One setting, `co.acme.lift_plan.max_load_tonnes` |
| `examples/` | Valid instances; each must validate against the body schema |
| `type.lock` | Content hash of every other file; `tl types lock <dir>` rewrites it |

Register it with `tl types sync schema/fixtures/types`.

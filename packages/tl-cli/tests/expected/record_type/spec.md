# Record type: inspection.WeldInspection

Status: draft. Written by: TODO. Module spec: docs/modules/inspection/README.md.

## Purpose
TODO: what a WeldInspection is and who creates it, in two or three sentences.

## Fields
| Field | Range | Required | Notes |
|---|---|---|---|
| example_field | string | no | TODO: replace with the fields of the type |

The envelope fields (id, key, scope, title, status, psets and the rest) come from `RecordEnvelope` in `schema/core/record.yaml`.

## Workflow
TODO: states and transitions, or "none".

## Expected links
TODO: the relations a WeldInspection is expected to have (`tl:expects_link`), or "none".

## Events
| Event type | Payload | Handler |
|---|---|---|
| WeldInspection.Created | record_type, key, title, description | `handle_create_weld_inspection` |

## Open questions
- TODO

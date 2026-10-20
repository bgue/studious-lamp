# Module spec: schemareg (the schema registry, brief 27.4)

Status: accepted (built in P1-I8). Brief sections: §27.4 to §27.9 (package lifecycle, classification, propagation, governance), §6.3 (conformance modes, waivers), §28 (the lake reads no package). Decisions: FANOUT `docs/tickets/P1-I8/FANOUT.md` D1 to D5, ADR-0010 (module storage), ADR-0013 (roles).

## Purpose
The schema registry keeps, in the ledger, the packages that change what a record may hold: the company standard psets and code lists, a project's extensions and its own psets, the project's pin of each company package, and the waivers that relax one property for a while. The directory of package files (`schema/fixtures`, `TL_SCHEMA_DIR`) stays the base layer; a published ledger package joins it (`tl_core.schema_provider.RegistryState`). Nothing here edits an event: a package is drafted, classified, reviewed and published by events, and the effective schema of a scope follows.

## Record types
| Type | Key | Table | Workflow |
|---|---|---|---|
| `schemareg.SchemaPackage` | `<package>@<version>` (`co.acme.engineering@3.3.0`) | `cur_schemareg_schema_package` | `schemareg.schema-package`: Draft, InReview, Approved, Published, Deprecated, Retired |
| `schemareg.Adoption` | `<project>/<package>` | `cur_schemareg_adoption` | none; a new pin is an event on the same record |
| `schemareg.Waiver` | `<project>/<path>@<n>` | `cur_schemareg_waiver` | `schemareg.waiver`: Requested, Approved, Revoked |

## Events
| Event type | Meaning |
|---|---|
| `SchemaPackage.Drafted` / `Revised` | The author wrote or changed the content (YAML, at most 256 KiB) |
| `SchemaPackage.Analysed` | The classification and impact reports for the content with a stated hash |
| `SchemaPackage.Submitted` / `ChangesRequested` / `Approved` | The review |
| `SchemaPackage.Published` | A core catalog event (feed card, webhooks): the version is adoptable; carries `record_id`, `kind`, `worst_class`, `content_sha256`, `auto_adopted` |
| `SchemaPackage.Deprecated` / `Retired` | No new adoptions; out of every effective schema |
| `Adoption.Pinned` | A project pinned a version (`previous_version`, `worst_class`, the digest of the impact report read, `auto`) |
| `Waiver.Requested` / `Approved` / `Revoked` | The waiver's life |

## The life of a package
1. `DraftSchemaPackage` (any signed-in person): the YAML is parsed; the scope is the package's own (`company`, or `project:<id>`); a name@version that is a file or already drafted is refused.
2. `AnalyseSchemaPackage` (the author): the version must be higher than every version in force; the package must compose into the scope's effective schema; the classification (`tl_schema.classify`) is made against the version below it, the impact report (`tl_mod_schemareg.impact`) against the schema before and after. A later `ReviseSchemaPackage` voids both.
3. `SubmitSchemaPackage` (the author): needs reports for the current content; refuses `breaking` and `forbidden` changes and lint errors.
4. `ApproveSchemaPackage` / `RequestSchemaChanges` (admin): the author and the submitter cannot approve.
5. `PublishSchemaPackage` (admin): needs an Approved package whose approval is for the stored classification, which still composes, and whose base version is still the one below it. With `auto_adopt`, projects that pin the version below move to this one when the change is purely additive.
6. `DeprecateSchemaPackage`, `RetireSchemaPackage` (admin): a version a project still pins is not retired.

## Adoption
`AdoptSchemaPackage` (admin) pins `package@version` for a project. An additive version needs nothing more; anything else (constraining, renaming, a downgrade) needs the digest of the project impact report, which the handler computes again and compares. A project whose own packages depend on another version of the same company package cannot pin until they are published against it. Company scope uses the highest version overall; a project uses its pin, else the highest *file* version, never a ledger-only version it has not pinned.

## Waivers
`RequestWaiver` (any signed-in person) names a property of the project's effective schema, a reason and an expiry (at most 366 days). `ApproveWaiver` (admin, not the requester) makes it part of the project's effective schema: the mode becomes `strict_with_waivers` unless the project's package declares a mode, and the waivers are listed with the approver. `RevokeWaiver` takes it out. A project whose package declares `strict` or `lenient` cannot have waivers (they would have no effect), and the request is refused.

## Conformance dashboard
`conformance_dashboard(conn, project)` (`tl schema conformance --project P [--json]`, any signed-in person) is one read of how a project's records stand: per record type how many are `ok`, `warning`, `nonconformant` and `waived` as stored, and how many were last checked against a schema other than the one in force now (stale; a record never checked counts as stale); the approved waivers with the days left (0 on the last day) and a count of approved waivers past their day; and the company packages the project is behind on. Nothing is re-evaluated. A record the reader may not see is not counted and a type only such records have does not appear (ADR-0016). A type's `total` is the sum of the four.

## Who can do what
| Act | Who |
|---|---|
| Draft, revise, analyse, submit a package; request a waiver | any signed-in person (the first four only the actor that drafted the package) |
| Send back, approve, publish, deprecate, retire; adopt; approve or revoke a waiver | admin |
| Reads | `document.read` |
| Agents | read only; no command of this module is proposable |

## Operations
Runbook: [schema-registry](../../runbooks/schema-registry.md). The registry source rereads the ledger within a second of a change in the same process and within `ttl` (1 s) of another process's change.

# AGENTS.md — tl-schema

Read the root `AGENTS.md` first. These rules add to it.

- Everything under `src/tl_schema/generated/` is generator output: change `schema/` or a generator, run `just gen`, commit both.
- Generators are deterministic: no timestamps, no absolute paths, sorted keys. LinkML generators run with the working directory set to `schema/core` and a relative file name.
- Modules that import `linkml` start with `# pyright: basic` (no type stubs). Everything else is pyright strict.
- A LinkML annotation is read only if `schema/core/annotations.yaml` names it. Add the tag there and the code that reads it in one change.
- Dialect-specific DDL may be emitted here (codegen), never executed here.
- `schema/**` changes need a ticket labelled `schema` and a named human approver.

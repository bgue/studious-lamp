# AGENTS.md — tl-schema

Read the root `AGENTS.md` first. These rules add to it.

- Everything under `src/tl_schema/generated/` is generator output: change `schema/` or a generator, run `just gen`, commit both.
- Generators are deterministic: no timestamps, no absolute paths, sorted keys. LinkML generators run with the working directory set to `schema/core` and a relative file name.
- Modules that import `linkml` start with `# pyright: basic` (no type stubs). Everything else is pyright strict.
- A LinkML annotation is read only if `schema/core/annotations.yaml` names it. Add the tag there and the code that reads it in one change.
- Dialect-specific DDL may be emitted here (codegen), never executed here.
- `schema/**` changes need a ticket labelled `schema` and a named human approver.
- Package files (`schema/fixtures/*.yaml`) are a constrained YAML subset; the document models forbid unknown keys, so "rename, remove, retype" cannot be written. A new rule for what projects may do is a `SchemaCompileError` with a `rule` code and a test in `tests/test_compile.py`.
- `EffectiveSchema` is immutable after `with_hash`. Anything a runtime reader depends on must be in the model and therefore in the hash (value meanings are; code-list descriptions are not).
- Reserved names: psets `x`, `prj`, `enrich`, `src`; property `x`. Names contain no double underscore (promoted column names rely on it).
- `required_in_states` containing `*` means every state. Use `states_cover` and `required_in`, never plain list comparisons.
- Tests share fixtures through `tests/conftest.py` fixtures (`build_docs`, `effective`, `fixture_dir`), not imports.

# tl-mod-documents (`tl_mod_documents`)

TODO: one sentence on what the documents module does and which brief sections it implements (§...).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_mod_documents.MODULE` | constant | The module name, `documents` |

## Depends on / used by
- Depends on: `tl_core`, `tl_schema`, `tl_adapters`.
- Used by: TODO.

## Commands
```
just test packages/tl-modules/documents
uv run tl new record-type documents.<Class>
uv run tl new projector documents.<name>
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Scaffolded by `tl new module documents`. Module spec: `docs/modules/documents/README.md`; schema: `schema/modules/documents/`.

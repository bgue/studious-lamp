# AGENTS.md — tl-adapters

Read the root `AGENTS.md` first. These rules add to it.

- Dialect-specific SQL lives only here (and, as generated DDL text, in `tl_schema`).
- Never UPDATE or DELETE rows of `events`; the triggers reject it and no code may route around them.
- SQLite transactions go through `write_tx` / `read_tx`. Do not reintroduce pysqlite's implicit transaction handling.
- `append_in` needs a connection from `write_tx`. Commit and bus enqueue happen under one lock; subscribers run after it is released.
- Parity: anything here that the Postgres adapter will mirror must be covered by a test that can run against both (parity suite arrives in P0-I5).
- pyright strict applies to `src/`. No ignores.
- Object stores: a `sha256/` key is written only by `put`, after size and SHA-256 are verified, and is never replaced. Presigned uploads (`presign_put`, `put_via_url`) accept staging keys only. Every key goes through `tl_core.files.keys.check_key` first.
- Tests use `FsObjectStore` or moto's in-process `mock_aws`; never a live MinIO, never the network. `s3.py` starts with `# pyright: basic` because boto3 has no stubs; keep that to the one file.
- `object_secret()` fails closed. Never add a default secret or log one.

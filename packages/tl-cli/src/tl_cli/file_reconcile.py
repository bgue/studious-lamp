"""`tl file reconcile`: compare the ledger's file rows with the object store (brief 24.5).

The command function is registered by `file.py`. It prints a summary and one line per problem and
exits 1 when anything is missing or corrupt. It never repairs: see the runbook
`docs/runbooks/object-store-reconciliation.md`.

STUB (P0-I4-T25): the signature is final; the body marked `raise NotImplementedError` is the
ticket. Remove this paragraph when done.
"""

from __future__ import annotations

from typing import Annotated

import typer


def reconcile(
    ctx: typer.Context,
    verify: Annotated[
        bool, typer.Option("--verify", help="Also re-hash every object (reads all bytes).")
    ] = False,
) -> None:
    """Report referenced hashes that are missing from the store, and orphaned objects."""
    raise NotImplementedError

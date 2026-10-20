"""Helper of `dev/demos/P1-I7B.sh`: an AI agent proposes a dispatch (no model involved).

``propose DB PROJECT KEY TEXT`` makes the account of agent ``triage`` if it is missing, plans TEXT
as the agent on the record named KEY and files the proposal the MCP tool files, printing its id.
Nothing runs until a person accepts it (`tl proposal accept`). A refusal prints one ``error:``
line and exits 1.
"""

from __future__ import annotations

import sys

from sqlalchemy import text
from tl_adapters.db import make_uow_factory, open_uow
from tl_api.thread_runner import thread_runner
from tl_core.auth import accounts
from tl_core.auth.errors import UsernameTakenError
from tl_core.services import proposals
from tl_core.threads.dispatch import build_dispatch_proposal

AGENT = "agent:triage"


def propose(db: str, project: str, key: str, line: str) -> None:
    with open_uow(db) as uow:
        try:
            accounts.create_account(
                uow,
                username="triage",
                display_name="triage",
                kind="agent",
                roles=["user"],
                password=None,
                by="user:demo",
            )
        except UsernameTakenError:
            pass
    with open_uow(db, readonly=True) as uow:
        record_id = str(
            uow.conn()
            .execute(text("SELECT id FROM cur_core_record WHERE key = :k"), {"k": key})
            .scalar_one()
        )
    factory = make_uow_factory(db)
    runner = thread_runner()
    try:
        command = build_dispatch_proposal(
            factory,
            scope=f"project:{project}",
            record_id=record_id,
            text=line,
            agent=AGENT,
            runner=runner,
        )
        view = proposals.submit(
            factory,
            tool="propose_dispatch",
            agent=AGENT,
            command=command,
            summary=f"Run {line} on {key}",
            runner=runner,
        )
    except Exception as exc:  # one line for the demo, whatever the refusal is
        print(f"error: {exc}")
        sys.exit(1)
    print(view.proposal_id)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "propose" and len(sys.argv) == 6:
        propose(*sys.argv[2:6])
    else:
        sys.exit("usage: p1_i7b_demo.py propose DB PROJECT KEY TEXT")


if __name__ == "__main__":
    main()

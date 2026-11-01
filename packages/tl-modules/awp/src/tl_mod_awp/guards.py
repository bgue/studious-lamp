"""State guards on the generic commands of a package (ADR-0010 addendum).

The allow-list in ``module.py`` says which generic commands may reach a type; a guard says when.
It runs in ``tl_core.modules.require_generic`` at the same places as the allow-list (the file upload
path included), after the record is known to be visible to the viewer.

* **CWP, every generic command it takes** (values, links, link life, files): ``not_closed``. A
  Closed or Void package is the record of what was built or abandoned and takes no more.
"""

from __future__ import annotations

from sqlalchemy import Connection
from tl_core.services.errors import UnsupportedRecordTypeError

from tl_mod_awp.common import package_state
from tl_mod_awp.names import ST_CLOSED, ST_VOID

MSG_CLOSED = "a closed or void package takes no more values, links or files"


def not_closed(conn: Connection, record_id: str, slot: str | None) -> None:
    """Refuse a generic command on a package that is Closed or Void."""
    del slot
    if package_state(conn, record_id) in (ST_CLOSED, ST_VOID):
        raise UnsupportedRecordTypeError(MSG_CLOSED)

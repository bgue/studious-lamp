"""The Details tab of a CWP (``awp.CWP``): the rows ``awp_text.cwp_rows`` builds, the same rows the
CWP's panel is cut from (P2-I1 T05a). The record key is the CWP number.
"""

from __future__ import annotations

from typing import Any

from tl_tui.awp_text import cwp_rows
from tl_tui.client import ClientInterface
from tl_tui.details import DetailRow, register
from tl_tui.display import Labels


@register("awp.CWP")
def cwp_details(
    client: ClientInterface, project: str, record: dict[str, Any], labels: Labels
) -> list[DetailRow]:
    return cwp_rows(client.get_cwp(project, str(record["key"])), labels)

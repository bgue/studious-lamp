"""The HTTP client WS-D wraps as the remote ``ClientInterface`` (brief 4).

``ApiClient(base_url, token)`` offers the ``ClientInterface`` methods with the same names,
parameters and return types, plus ``query_records``/``count_records`` (O3), the file calls and
the event feed.
See ``tl_api.client.base`` for how errors map back to exceptions.
"""

from tl_api.client.base import ApiClientBase
from tl_api.client.events import EventsApi
from tl_api.client.files import FilesApi
from tl_api.client.links import LinksApi
from tl_api.client.records import RecordsApi


class ApiClient(RecordsApi, LinksApi, FilesApi, EventsApi):
    """One connection, every group of methods."""


__all__ = ["ApiClient", "ApiClientBase"]

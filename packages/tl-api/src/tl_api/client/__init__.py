"""The HTTP client WS-D wraps as the remote ``ClientInterface`` (brief 4).

``ApiClient(base_url, token)`` offers the ``ClientInterface`` methods with the same names,
parameters and return types, plus ``query_records``/``count_records`` (O3), the file calls, the
event feed, the about:config settings calls and the account calls (`tl_api.client.auth.sign_in`
and the admin module).
See ``tl_api.client.base`` for how errors map back to exceptions.
"""

from tl_api.client.admin import AdminApi
from tl_api.client.auth import AuthApi
from tl_api.client.base import ApiClientBase
from tl_api.client.engineering import EngineeringApi
from tl_api.client.events import EventsApi
from tl_api.client.feed import FeedApi
from tl_api.client.files import FilesApi
from tl_api.client.links import LinksApi
from tl_api.client.proposals import ProposalsApi
from tl_api.client.records import RecordsApi
from tl_api.client.settings import SettingsApi
from tl_api.client.types_api import TypesApi


class ApiClient(
    RecordsApi,
    LinksApi,
    FilesApi,
    EventsApi,
    FeedApi,
    ProposalsApi,
    SettingsApi,
    TypesApi,
    EngineeringApi,
    AuthApi,
    AdminApi,
):
    """One connection, every group of methods."""


__all__ = ["ApiClient", "ApiClientBase"]

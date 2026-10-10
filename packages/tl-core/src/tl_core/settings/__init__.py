"""Settings (about:config v1, brief 30): definitions, resolution, changes and the reader.

The contracts are in :mod:`tl_core.settings.types` (frozen for P0-I8). The pieces:

* :mod:`~tl_core.settings.registry`: the platform file and registered extension keys;
* :mod:`~tl_core.settings.resolver`: layer resolution, history and diff over ``cur_setting``;
* :mod:`~tl_core.settings.service`: set, reset, lock and revert, with every check;
* :mod:`~tl_core.settings.exchange`: YAML export and import of one layer;
* :mod:`~tl_core.settings.reader`: the cached, bus-invalidated reader for code that asks often.
"""

from tl_core.settings.exchange import export_yaml, import_yaml
from tl_core.settings.reader import SettingsReader, conn_factory_from, reader
from tl_core.settings.registry import (
    definitions,
    get_definition,
    register_definitions,
    unregister_definitions,
)
from tl_core.settings.resolver import diff, history, resolve, resolve_all, value_of
from tl_core.settings.service import lock_setting, reset_setting, revert_setting, set_setting

__all__ = [
    "SettingsReader",
    "conn_factory_from",
    "definitions",
    "diff",
    "export_yaml",
    "get_definition",
    "history",
    "import_yaml",
    "lock_setting",
    "reader",
    "register_definitions",
    "reset_setting",
    "resolve",
    "resolve_all",
    "revert_setting",
    "set_setting",
    "unregister_definitions",
    "value_of",
]

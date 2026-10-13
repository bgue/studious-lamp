"""Names the engineering module shares: record types, event types, table names, kinds.

Plain constants, so a projector, a handler, a CLI command and a test all spell them the same way.
The record types and event types are documented in ``docs/modules/engineering/README.md`` and
catalogued in ``schema/modules/engineering/events.yaml``.
"""

from __future__ import annotations

from typing import Final

# Record types. Each is a row of cur_core_record and a row of the table named below.
CODE_LIST: Final = "engineering.CodeList"
MNEMONIC: Final = "engineering.Mnemonic"
NUMBERING_PATTERN: Final = "engineering.NumberingPattern"
CODE_VALUE: Final = "engineering.CodeValue"
TAG_CLASS: Final = "engineering.TagClass"
TAG: Final = "engineering.Tag"

RECORD_TYPES: Final = frozenset(
    {CODE_LIST, MNEMONIC, NUMBERING_PATTERN, CODE_VALUE, TAG_CLASS, TAG}
)

#: The ``kind`` column of ``cur_engineering_standard`` for each record type that lives in it.
STANDARD_KIND: Final = {
    CODE_LIST: "code_list",
    MNEMONIC: "mnemonic",
    NUMBERING_PATTERN: "numbering_pattern",
}

# Tables (generated from schema/modules/engineering/*.yaml).
STANDARD_TABLE: Final = "cur_engineering_standard"
CODE_VALUE_TABLE: Final = "cur_engineering_code_value"
TAG_CLASS_TABLE: Final = "cur_engineering_tag_class"
TAG_TABLE: Final = "cur_engineering_tag"

# Event types. The *Defined event follows Record.Created in the same append.
STANDARD_DEFINED: Final = "Standard.Defined"
STANDARD_CLOSED: Final = "Standard.Closed"
CODE_VALUE_DEFINED: Final = "CodeValue.Defined"
CODE_VALUE_CLOSED: Final = "CodeValue.Closed"
TAG_CLASS_DEFINED: Final = "TagClass.Defined"
TAG_CLASS_REVISED: Final = "TagClass.Revised"
TAG_CLASS_CLOSED: Final = "TagClass.Closed"
TAG_DEFINED: Final = "Tag.Defined"
TAG_RECLASSIFIED: Final = "Tag.Reclassified"
TAG_SUPERSEDED: Final = "Tag.Superseded"

#: The scope of the company registry.
COMPANY: Final = "company"

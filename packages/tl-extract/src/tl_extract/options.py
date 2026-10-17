"""The options of the tabular extractor, checked before any byte is read (P1-I3B-S1).

``extract(source, data, options)`` takes a free mapping. A misspelt option name must not be
ignored silently (the person would think a mapping was applied), so every key is checked.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tl_extract.reading import MAX_HEADER_CHARS, MAX_HEADER_ROW, Refusal, shown

Delimiter = Literal[",", ";", "\t", "|"]


class TableOptions(BaseModel):
    """Options of ``TabularExtractor.extract``.

    * ``sheet``: the XLSX sheet to read, by name; default the first worksheet.
    * ``header_row``: the 1-based record that holds the column names (rows above it are skipped).
    * ``delimiter``: the CSV delimiter; default detected from the header record.
    * ``header_map``: column-name hints, ``{"TAG NO": "tag_number"}``. A header matches a hint
      when both are the same after lower-casing and replacing every run of characters that are
      not letters or digits by ``_`` (``Tag No.`` matches ``TAG NO``). The result uses the hint's
      value exactly as written.
    * ``normalise_headers``: write the headers that no hint named as lower-case ``snake_case``.
    * ``duplicate_headers``: ``refuse`` (default) fails the file when two columns end up with the
      same name; ``suffix`` keeps the first and names the others ``name_2``, ``name_3``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    sheet: Annotated[str, Field(min_length=1, max_length=MAX_HEADER_CHARS)] | None = None
    header_row: Annotated[int, Field(ge=1, le=MAX_HEADER_ROW)] = 1
    delimiter: Delimiter | None = None
    header_map: dict[
        Annotated[str, Field(min_length=1, max_length=MAX_HEADER_CHARS)],
        Annotated[str, Field(min_length=1, max_length=MAX_HEADER_CHARS)],
    ] = Field(default_factory=dict[str, str], max_length=200)
    normalise_headers: bool = False
    duplicate_headers: Literal["refuse", "suffix"] = "refuse"


def parse_options(options: Mapping[str, Any]) -> TableOptions:
    """Validate ``options``. Raises ``Refusal("bad_option", ...)`` naming the option and the rule,
    never echoing the value."""
    try:
        return TableOptions.model_validate(dict(options))
    except ValidationError as exc:
        error = exc.errors()[0]
        where = shown(".".join(str(part) for part in error["loc"][:1])) or "options"
        raise Refusal("bad_option", f"option {where}: {error['msg']}") from exc

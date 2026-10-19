"""Pieces of command models the item commands share: a recipient, vocabularies, text checks.

The limits of ``limits.py`` bound every list and text before a handler reads it (the P1-I1 security
review rule); an unknown field is refused (``extra="forbid"``) by every model of this module.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tl_mod_correspondence.limits import MAX_EMAIL, MAX_NUMBER, MAX_TEXT
from tl_mod_correspondence.textcheck import clean_text

Medium = Literal["letter", "email", "portal", "minutes", "other"]
Via = Literal["upload", "email", "manual"]
PartyRole = Literal[
    "client",
    "engineer",
    "contractor",
    "subcontractor",
    "supplier",
    "authority",
    "internal",
    "other",
]

_EMAIL = re.compile(r"[^@\s<>()\[\]\\,;:\"]{1,64}@[A-Za-z0-9.-]{1,190}")


def non_blank(value: str) -> str:
    """``value`` when it has a visible character and no control or direction character (it
    becomes record text, so it is checked like any text from outside)."""
    if not value.strip():
        raise ValueError("must not be blank")
    return clean_text(value)


class Recipient(BaseModel):
    """Who a letter is to or copied to: a name, an email address, a known party, or any of them."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=MAX_TEXT)
    email: str | None = Field(default=None, max_length=MAX_EMAIL)
    party_id: str | None = Field(default=None, max_length=MAX_NUMBER)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = clean_text(value).strip()
        return cleaned or None

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        address = value.strip().lower()
        if _EMAIL.fullmatch(address) is None:
            raise ValueError(f"{value!r} is not an email address")
        return address

    @model_validator(mode="after")
    def _something(self) -> Recipient:
        if self.name is None and self.email is None and self.party_id is None:
            raise ValueError("a recipient needs a name, an email address or a party")
        return self

    def as_payload(self) -> dict[str, Any]:
        return {"name": self.name, "email": self.email, "party_id": self.party_id}

"""Test support other packages share: a registry in a ledger without running the registry commands.

``seed_registry`` writes the entries the tag tests, the CLI tests and the demos rely on with raw
appends of the events the registry commands would write, so a test of tags needs neither the
standards file nor the registry handlers. It is not registered anywhere and never runs in
production.
"""

from __future__ import annotations

from typing import Any

from tl_mod_engineering.names import COMPANY


def seed_registry(db: Any) -> None:
    """Register the area list, mnemonics, the tag pattern and two tag classes in a ledger.

    Writes the records with raw appends (the registry commands are not needed): list Area with
    values 10 and 47, mnemonics FV, PV, HV and PT, the pattern ``tag`` and the classes
    ControlValve (psets valve_data; mnemonics FV, PV) and ManualValve (valve_data; HV).
    """
    from tl_adapters.db import open_uow
    from tl_core.ledger import NewEvent

    edition = "co.acme.standards@1.0.0"

    def put(
        uow: Any,
        stream: str,
        record_type: str,
        key: str,
        scope: str,
        defined: tuple[str, dict[str, Any]],
    ) -> None:
        uow.append(
            stream_id=stream,
            stream_type=record_type,
            scope=scope,
            expected_version=0,
            events=[
                NewEvent(
                    event_type="Record.Created",
                    payload={"record_type": record_type, "key": key, "title": key, "psets": {}},
                ),
                NewEvent(event_type=defined[0], payload=defined[1]),
            ],
            actor="user:seed",
            source="test",
            correlation_id="seed",
        )

    def standard(kind: str, code: str, **data: Any) -> tuple[str, dict[str, Any]]:
        return "Standard.Defined", {
            "kind": kind,
            "code": code,
            "label": code,
            "edition": edition,
            "data": data,
            "value_list_policy": "extensible" if kind == "code_list" else None,
        }

    with open_uow(db) as uow:
        put(
            uow,
            "S-Area",
            "engineering.CodeList",
            "CL:Area@1.0.0",
            COMPANY,
            standard("code_list", "Area"),
        )
        for code in ("10", "47"):
            put(
                uow,
                f"V-{code}",
                "engineering.CodeValue",
                f"CV:Area.{code}@1.0.0",
                COMPANY,
                (
                    "CodeValue.Defined",
                    {
                        "code_list": "Area",
                        "code": code,
                        "label": code,
                        "origin": "company",
                        "edition": edition,
                    },
                ),
            )
        for code in ("FV", "PV", "HV", "PT"):
            put(
                uow,
                f"S-{code}",
                "engineering.Mnemonic",
                f"MN:{code}@1.0.0",
                COMPANY,
                standard("mnemonic", code),
            )
        put(
            uow,
            "S-tag",
            "engineering.NumberingPattern",
            "NP:tag@1.0.0",
            COMPANY,
            standard(
                "numbering_pattern",
                "tag",
                record_type="engineering.Tag",
                template="{area}-{mnemonic}-{seq:4}",
                segments={
                    "area": {"role": "area", "list": "Area", "registry": None},
                    "mnemonic": {"role": "mnemonic", "list": None, "registry": "mnemonic"},
                    "seq": {"role": "sequence", "list": None, "registry": None},
                },
                allocate=False,
                gap_free=True,
                scope="project:*",
                reserved=[],
            ),
        )
        for code, mnemonics in (("ControlValve", ["FV", "PV"]), ("ManualValve", ["HV"])):
            put(
                uow,
                f"C-{code}",
                "engineering.TagClass",
                f"TC:{code}",
                COMPANY,
                (
                    "TagClass.Defined",
                    {
                        "code": code,
                        "label": code,
                        "family": "valve",
                        "required_psets": ["valve_data"],
                        "itr_templates": [],
                        "mnemonics": mnemonics,
                        "edition": edition,
                    },
                ),
            )

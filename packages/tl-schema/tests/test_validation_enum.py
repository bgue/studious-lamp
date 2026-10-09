"""An enum property without values must not reject every value (T04 follow-up)."""

from __future__ import annotations

from tl_schema.effective import EffectiveSchema
from tl_schema.validation import record_json_schema, validate_psets


def test_an_enum_without_values_is_unconstrained(effective: EffectiveSchema) -> None:
    data = effective.model_dump(mode="json")
    data["psets"]["valve_data"]["properties"]["fail_action"]["enum_values"] = None
    data["hash"] = "enum-none"
    schema = EffectiveSchema.model_validate(data)
    props = record_json_schema(schema, "core.Record")["properties"]["valve_data"]["properties"]
    assert "enum" not in props["fail_action"]
    assert props["fail_action"]["type"] == "string"
    assert validate_psets(schema, "core.Record", {"valve_data": {"fail_action": "ANY"}}) == []

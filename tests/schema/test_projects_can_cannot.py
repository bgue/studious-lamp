"""Every row of the brief 6.3 "projects can / projects cannot" table, end to end (P0-I2-T09).

Each test copies the fixture packages, applies the change a project would try, and drives the real
provider, handler and conformance evaluator against a SQLite ledger.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.commands import CommandResult, CreateRecord
from tl_core.services.errors import LayerError, UnknownPsetError
from tl_core.services.psets import (
    SetPsetValues,
    conformance,
    form_metadata,
    handle_set_pset_values,
)
from tl_core.services.records import handle_create_record
from tl_schema.compile import SchemaCompileError
from tl_schema.registry import PackageError

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures"
SCOPE = "project:P123"
GOOD = {"size_in": 4, "manufacturer": "Acme"}  # satisfies every always-required property

Data = dict[str, Any]
Edit = Callable[[Data], object]


class World:
    """A copy of the fixture packages, a provider over it, and a ledger."""

    def __init__(self, tmp_path: Path, new_db: Callable[[], DbTarget]) -> None:
        self.packages = tmp_path / "pkgs"
        shutil.copytree(FIXTURES, self.packages)
        self.provider = DirectorySchemaProvider(self.packages)
        self.db = new_db()
        create_schema(self.db)
        self.records = 0

    def edit(self, filename: str, change: Edit) -> None:
        path = self.packages / filename
        data: Data = yaml.safe_load(path.read_text())
        change(data)
        path.write_text(yaml.safe_dump(data, sort_keys=False))

    def ext(self, change: Callable[[Data], object]) -> None:
        """Edit the first ``extends`` entry of the project extension."""
        self.edit("x.P123@1.4.0.yaml", lambda d: change(d["extends"][0]))

    def company(self, change: Edit) -> None:
        self.edit("co.acme.engineering@3.2.0.yaml", change)

    def record(self, scope: str = SCOPE) -> CommandResult:
        self.records += 1
        key = f"V-{self.records}"
        with open_uow(self.db) as uow:
            return handle_create_record(
                uow,
                CreateRecord(
                    actor="user:u",
                    source="test",
                    scope=scope,
                    record_type="core.Record",
                    title="Valve",
                    key=key,
                ),
            )

    def write(
        self,
        pset: str,
        values: Data,
        *,
        layer: str = "standard",
        scope: str = SCOPE,
        record: CommandResult | None = None,
    ) -> CommandResult:
        target = record or self.record(scope=scope)
        cmd = SetPsetValues.model_validate(
            {
                "actor": "user:u",
                "source": "test",
                "scope": scope,
                "stream_id": target.stream_id,
                "expected_version": target.version,
                "pset": pset,
                "layer": layer,
                "values": values,
            }
        )
        with open_uow(self.db) as uow:
            return handle_set_pset_values(uow, cmd)

    def status(self, result: CommandResult) -> str:
        return str(result.events[0].payload["conformance"])


@pytest.fixture
def world(tmp_path: Path, new_db: Callable[[], DbTarget]) -> Iterator[World]:
    built = World(tmp_path, new_db)
    with use_provider(built.provider):
        yield built


# --- projects can ------------------------------------------------------------------------------


def test_can_add_values_to_an_extensible_list_with_a_crosswalk(world: World) -> None:
    values = {**GOOD, "body_material": "SS316L-NACE"}
    assert world.status(world.write("valve_data", values)) == "ok"
    # The company schema does not know the project's code.
    assert world.status(world.write("valve_data", values, scope="company")) == "nonconformant"


def test_can_own_a_project_defined_list_outright(world: World) -> None:
    def company(data: Data) -> None:
        data["psets"]["valve_data"]["properties"]["body_material"]["value_list_policy"] = (
            "project_defined"
        )

    def extension(entry: Data) -> None:
        entry["add_values"]["MaterialCode"] = [{"code": "INCONEL", "label": "Inconel 625"}]

    world.company(company)
    world.ext(extension)
    values = {**GOOD, "body_material": "INCONEL"}
    assert world.status(world.write("valve_data", values)) == "ok"
    assert world.status(world.write("valve_data", values, scope="company")) == "nonconformant"


def test_can_add_custom_section_properties_to_a_pset_that_is_not_locked(world: World) -> None:
    result = world.write("valve_data", {"x.fat_witness_by": "client"}, layer="custom")
    assert result.events[0].payload["values"] == {"x.fat_witness_by": "client"}
    paths = [f.path for g in form_metadata_of(world).psets for f in g.fields]
    assert "psets.valve_data.x.fat_witness_by" in paths
    assert "psets.valve_data.x.tie_in_window" in paths


def form_metadata_of(world: World, scope: str = SCOPE, record_type: str = "core.Record") -> Any:
    with open_uow(world.db, readonly=True) as uow:
        return form_metadata(uow, scope, record_type)


def test_can_tighten_a_range(world: World) -> None:
    world.ext(lambda e: e["tighten"].update({"size_in": {"minimum": 1, "maximum": 48}}))
    inside = world.write("valve_data", GOOD)
    assert world.status(inside) == "ok"
    low = {"size_in": 0.5, "manufacturer": "Acme"}
    assert world.status(world.write("valve_data", low)) == "nonconformant"
    assert world.status(world.write("valve_data", low, scope="company")) == "ok"


def test_can_make_an_optional_property_required(world: World) -> None:
    world.ext(
        lambda e: e["tighten"].update(
            {"tag_no": {"required_in_states": ["*"], "enforcement": "required"}}
        )
    )
    result = world.write("valve_data", GOOD)
    assert world.status(result) == "nonconformant"  # tag_no is now required
    report = conformance_of(world, result)
    assert [(i.path, i.rule) for i in report] == [("psets.valve_data.tag_no", "required_in_state")]
    assert world.status(world.write("valve_data", GOOD, scope="company")) == "ok"


def conformance_of(world: World, result: CommandResult) -> Any:
    with open_uow(world.db, readonly=True) as uow:
        return conformance(uow, result.stream_id).issues


def test_can_set_project_defaults_and_labels(world: World) -> None:
    world.ext(lambda e: e.update({"defaults": {"size_in": 2}, "labels": {"size_in": "NPS (in)"}}))
    prop = world.provider.effective(SCOPE).psets["valve_data"].properties["size_in"]
    assert (prop.default, prop.label) == (2, "NPS (in)")
    fields = {f.path: f for g in form_metadata_of(world).psets for f in g.fields}
    assert fields["psets.valve_data.size_in"].label == "NPS (in)"
    company = world.provider.effective("company").psets["valve_data"].properties["size_in"]
    assert (company.default, company.label) == (None, "Nominal size")


def test_can_create_project_psets_and_bind_them_to_any_record_type(world: World) -> None:
    world.edit(
        "prj.P123@1.0.0.yaml",
        lambda d: d["psets"]["shutdown_tie_in"].update({"applies_to": ["piping.Weld"]}),
    )
    weld = form_metadata_of(world, record_type="piping.Weld")
    assert [g.name for g in weld.psets] == ["prj.shutdown_tie_in"]
    with pytest.raises(UnknownPsetError):  # it no longer applies to core.Record
        world.write("prj.shutdown_tie_in", {"window": "SD-1"}, layer="project")
    world.edit(
        "prj.P123@1.0.0.yaml",
        lambda d: d["psets"]["shutdown_tie_in"].update(
            {"applies_to": ["piping.Weld", "core.Record"]}
        ),
    )
    assert world.write("prj.shutdown_tie_in", {"window": "SD-1"}, layer="project").version == 2


# --- projects cannot ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["remove", "rename", "rename_to"])
def test_cannot_remove_or_rename_a_company_property(world: World, key: str) -> None:
    world.ext(lambda e: e.update({key: {"size_in": "length_in"}}))
    with pytest.raises(PackageError):
        world.provider.effective(SCOPE)


def test_cannot_shadow_a_company_property_with_a_custom_one(world: World) -> None:
    world.ext(
        lambda e: e["custom"].update({"size_in": {"description": "Mine.", "range": "string"}})
    )
    with pytest.raises(SchemaCompileError) as caught:
        world.provider.effective(SCOPE)
    assert caught.value.rule == "shadow"


@pytest.mark.parametrize("key", ["range", "unit", "description"])
def test_cannot_change_a_company_propertys_type_unit_or_meaning(world: World, key: str) -> None:
    world.ext(lambda e: e["tighten"].update({"size_in": {key: "something else"}}))
    with pytest.raises(PackageError):
        world.provider.effective(SCOPE)


@pytest.mark.parametrize(
    "tighten",
    [
        {"size_in": {"required_in_states": ["Design"]}},
        {"size_in": {"minimum": 0.1}},
        {"size_in": {"maximum": 500}},
        {"size_in": {"enforcement": "advisory"}},
        {"tag_no": {"pattern": "^.*$"}},
    ],
)
def test_cannot_loosen_a_company_constraint(world: World, tighten: Data) -> None:
    world.ext(lambda e: e["tighten"].update(tighten))
    with pytest.raises(SchemaCompileError) as caught:
        world.provider.effective(SCOPE)
    assert caught.value.rule == "loosen"


def test_cannot_touch_a_locked_pset_beyond_filling_values(world: World) -> None:
    world.ext(lambda e: None)
    world.edit(
        "x.P123@1.4.0.yaml",
        lambda d: d["extends"].append(
            {"ref": "co.acme.engineering@3.2.0#safety_data", "labels": {"sil_rating": "SIL"}}
        ),
    )
    with pytest.raises(SchemaCompileError) as caught:
        world.provider.effective(SCOPE)
    assert caught.value.rule == "locked"


def test_cannot_touch_a_locked_property(world: World) -> None:
    world.ext(lambda e: e["tighten"].update({"fail_action": {"required_in_states": ["Design"]}}))
    with pytest.raises(SchemaCompileError) as caught:
        world.provider.effective(SCOPE)
    assert caught.value.rule == "locked"


def test_cannot_add_values_to_a_closed_list(world: World) -> None:
    world.ext(lambda e: e["add_values"].update({"FailAction": [{"code": "FX", "label": "Exotic"}]}))
    with pytest.raises(SchemaCompileError) as caught:
        world.provider.effective(SCOPE)
    assert caught.value.rule == "closed_list"


def test_locked_psets_accept_values_but_no_custom_section(world: World) -> None:
    filled = world.write("safety_data", {"sil_rating": 2}, scope="company")
    assert world.status(filled) == "ok"
    with pytest.raises(LayerError):
        world.write("safety_data", {"x.note": "n"}, layer="custom", scope="company")


def test_cannot_bypass_enforcement_without_a_waiver(world: World) -> None:
    bad = {"size_in": 500, "manufacturer": "Acme"}
    result = world.write("valve_data", bad)
    assert world.status(result) == "nonconformant"  # stored, flagged, never silently accepted
    [issue] = conformance_of(world, result)
    assert (issue.path, issue.rule, issue.level) == (
        "psets.valve_data.size_in",
        "range",
        "nonconformant",
    )


def waive(path: str, expires: str | None) -> Edit:
    def change(data: Data) -> None:
        waiver: Data = {"path": path, "reason": "Legacy data.", "approver": "user:dm"}
        if expires is not None:
            waiver["expires"] = expires
        data["conformance"] = {"mode": "strict_with_waivers", "waivers": [waiver]}

    return change


def test_a_waiver_is_the_only_way_to_relax_one_property(world: World) -> None:
    world.edit("x.P123@1.4.0.yaml", waive("psets.valve_data.size_in", "2099-01-01"))
    bad = {"size_in": 500, "manufacturer": "Acme"}
    assert world.status(world.write("valve_data", bad)) == "waived"
    other = {"size_in": 4, "manufacturer": "Acme", "tag_no": "bad"}
    assert world.status(world.write("valve_data", other)) == "warning"  # other issues still show


def test_an_expired_waiver_relaxes_nothing(world: World) -> None:
    world.edit("x.P123@1.4.0.yaml", waive("psets.valve_data.size_in", "2020-01-01"))
    bad = {"size_in": 500, "manufacturer": "Acme"}
    assert world.status(world.write("valve_data", bad)) == "nonconformant"


def test_lenient_mode_does_not_hide_data_errors(world: World) -> None:
    world.edit("x.P123@1.4.0.yaml", lambda d: d.update({"conformance": {"mode": "lenient"}}))
    bad = {"size_in": 500, "manufacturer": "Acme"}
    assert world.status(world.write("valve_data", bad)) == "nonconformant"


@pytest.mark.parametrize(
    ("pset", "values"),
    [
        ("enrich.ai_classifier", {"valve_type": "ball"}),
        ("src.ifc.Pset_ValveTypeCommon", {"Size": 4}),
    ],
)
def test_cannot_write_into_enrichment_or_source_layers(
    world: World, pset: str, values: Data
) -> None:
    with pytest.raises(LayerError):
        world.write(pset, values)

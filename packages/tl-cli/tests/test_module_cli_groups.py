"""The module CLI groups come from ``ModuleSpec.cli_groups`` (P2-X4-T01).

The top-level group names of ``tl`` are pinned by ``OLD_GROUPS``, captured from the root app before
the module lines were replaced by the hook loop. The set may not change; the order may.
"""

from __future__ import annotations

import logging

import pytest
import typer
from tl_cli.main import _add_module_groups, _group_name, app
from tl_core.modules import ModuleSpec, load_modules, resolve_hook, use_modules

# Captured from ``app.registered_groups`` before the loop replaced the module lines.
OLD_GROUPS = [
    "record",
    "events",
    "schema",
    "pset",
    "wf",
    "file",
    "link",
    "feed",
    "thread",
    "proposal",
    "standards",
    "tag",
    "doc",
    "derive",
    "xer",
    "load",
    "cost",
    "awp",
    "constraint",
    "transmittal",
    "review",
    "corr",
    "rfi",
    "comm",
    "mat",
    "punch",
    "insp",  # P2-INSP-T04 (tl insp, the quality module group)
    "req",
    "wo",
    "config",
    "types",
    "lake",
    "dev",
    "new",
    "webhook",
    "rule",
    "endpoint",
    "delivery",
    "enrich",
    "enricher",
    "action",
    "integration",
    "sim",
    "admin",
    "agent",  # P2-X2 T02 (tl agent stop|resume|stopped), merged after the baseline was captured
    "backup",
    "archive",
    "ledger",
    "projections",
    "qr",  # P2-QR S2 (the module's own group, by hook)
    "permit",  # P2-PTW S2: the permits module groups (empty until T04, T05)
    "isolation",
    "gastest",
    "checklist",  # P2-INSP-T05 (tl checklist, the quality module's group by hook)
    "form",  # V3-F1a (tl form, the forms module's group by hook)
    "intake",  # V3-F4 (tl intake, the forms module's second group by hook)
]

OLD_SUBGROUPS = {
    "corr": ["clock", "thread", "party", "clause", "class", "clearance", "mail", "report"],
    "doc": ["rev", "rendition", "report"],
    "tag": ["report"],
}


def _named(group_list: object) -> list[str]:
    return [group.name for group in group_list]  # type: ignore[attr-defined]


def test_top_level_group_names_are_unchanged() -> None:
    assert set(_named(app.registered_groups)) == set(OLD_GROUPS)


def test_corr_doc_and_tag_sub_group_names_are_unchanged() -> None:
    from tl_cli import corr, doc, tag

    assert set(_named(corr.app.registered_groups)) == set(OLD_SUBGROUPS["corr"])
    assert set(_named(doc.app.registered_groups)) == set(OLD_SUBGROUPS["doc"])
    assert set(_named(tag.app.registered_groups)) == set(OLD_SUBGROUPS["tag"])


def test_group_name_takes_the_module_for_app_and_the_prefix_for_x_app() -> None:
    assert _group_name("tl_cli.corr:app") == "corr"
    assert _group_name("tl_cli.req:wo_app") == "wo"


def test_group_name_refuses_any_other_attribute() -> None:
    with pytest.raises(ValueError) as err:
        _group_name("tl_cli.x:thing")
    assert "tl_cli.x" in str(err.value)
    assert "thing" not in str(err.value)


def test_every_installed_module_cli_group_resolves_to_a_typer() -> None:
    for spec in load_modules():
        groups = resolve_hook(spec, "cli_groups")
        assert len(groups) == len(spec.cli_groups), spec.name
        assert all(isinstance(group, typer.Typer) for group in groups), spec.name


def test_a_module_with_a_missing_group_object_loses_only_its_groups(
    caplog: pytest.LogCaptureFixture,
) -> None:
    by_name = {spec.name: spec for spec in load_modules()}
    cost: ModuleSpec = by_name["cost"]
    broken = ModuleSpec(
        name="awp",
        record_types=frozenset({"awp.Thing"}),
        projectors=list,
        cli_groups=("tl_cli.awp:NOPE_app",),
    )
    root = typer.Typer()
    with use_modules([broken, cost]), caplog.at_level(logging.WARNING, logger="tl_cli"):
        _add_module_groups(root, load_modules())
    names = [group.name for group in root.registered_groups]
    assert names == ["cost"]
    messages = [record.getMessage() for record in caplog.records if record.name == "tl_cli"]
    assert len(messages) == 1
    assert "NOPE" not in messages[0]
    assert "tl_cli.awp" not in messages[0]

"""The offline capture hook (OC-S2): every branch of ``capture_allowed``, node kind, streams.

The expectations come from ``docs/build-spec/specs/offline-classes.md`` section 4 and 5, written
out here (class table and drafting commands), not read back from the modules.
"""

from __future__ import annotations

from typing import Any

import pytest
from tl_core import offline
from tl_core.auth.module_roles import normalise_word
from tl_core.modules import ModuleSpec, load_modules, use_modules
from tl_core.offline import (
    NodeKind,
    NodeKindNotBuiltError,
    OfflineDecision,
    OnlineOnlyError,
    capture_allowed,
    is_authority,
    node_kind,
    offline_class,
    record_type_rows,
    require_capture_allowed,
    require_node_built,
    stream_class,
)
from tl_schema.generated.offline_classes import OFFLINE_CLASSES

NODES: tuple[NodeKind, ...] = ("authority", "site", "device")
OFFLINE_NODES: tuple[NodeKind, ...] = ("site", "device")
GENERIC = ("AddLink", "AttachFile", "SetPsetValues", "TransitionWorkflow")

SECTION_4_DRAFTS: dict[str, frozenset[str]] = {
    "documents.Document": frozenset({"RegisterDocument", "UpdateDocument"}),
    "documents.Revision": frozenset({"CreateRevision", "VoidRevision"}),
    "documents.Rendition": frozenset({"AttachRendition"}),
    "documents.Transmittal": frozenset({"CreateTransmittal", "VoidTransmittal"}),
    "correspondence.Correspondence": frozenset(
        {"DraftCorrespondence", "UpdateCorrespondence", "VoidDraft"}
    ),
    "correspondence.TechnicalItem": frozenset({"RaiseTechnical", "UpdateTechnical"}),
    "materials.StockLot": frozenset({"IssueStock", "TransferStock", "ReturnStock"}),
}
CENTRAL = ("controller", "admin", "company")


@pytest.fixture(autouse=True)
def authority_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(offline.NODE_KIND_VARIABLE, raising=False)


def stand_in(**kw: Any) -> ModuleSpec:
    return ModuleSpec(projectors=lambda: [], **kw)  # type: ignore[arg-type]


def oracle(record_type: str, command: str, word: str | None, node: str) -> tuple[bool, str]:
    """The rule of section 5 item 3, written independently of ``offline.py``."""
    if node == "authority":
        return True, "authority"
    declared = OFFLINE_CLASSES.get(record_type)
    if declared is None:
        return False, "unknown_type"
    if word in CENTRAL:
        return False, "central_act"
    if declared == "none":
        return False, "online_only"
    if declared == "full":
        return True, "full"
    if command in SECTION_4_DRAFTS.get(record_type, frozenset()):
        return True, "draft"
    return False, "not_drafting"


def test_the_decision_equals_the_rule_for_every_type_command_and_node() -> None:
    # a fine word (``materials.library.edit``) is read as its table word, as the resolver reads it
    words = {
        spec.name: {c: normalise_word(w) for c, w in spec.command_words.items()}
        for spec in load_modules()
    }
    rows = 0
    for record_type in OFFLINE_CLASSES:
        commands = {**words.get(record_type.split(".")[0], {}), **dict.fromkeys(GENERIC)}
        for command, word in commands.items():
            for node in NODES:
                got = capture_allowed(record_type, command, node=node)
                assert (got.allowed, got.reason) == oracle(record_type, command, word, node), (
                    node,
                    record_type,
                    command,
                )
                rows += 1
    assert rows > 1000


def test_the_authority_allows_everything_even_an_unknown_type() -> None:
    assert capture_allowed("x.Unknown", "Anything", node="authority") == OfflineDecision(
        allowed=True, reason="authority"
    )
    assert capture_allowed("documents.Revision", "IssueRevision", node="authority").allowed
    assert capture_allowed("cost.CostCode", "ImportCostSnapshot", node="authority").allowed


@pytest.mark.parametrize("node", OFFLINE_NODES)
def test_an_unknown_type_is_refused_on_a_site_and_a_device(node: NodeKind) -> None:
    got = capture_allowed("x.Unknown", "Anything", node=node)
    assert (got.allowed, got.reason) == (False, "unknown_type")


@pytest.mark.parametrize("node", OFFLINE_NODES)
def test_a_controller_command_on_a_draft_only_type_is_a_central_act(node: NodeKind) -> None:
    got = capture_allowed("documents.Revision", "IssueRevision", node=node)
    assert (got.allowed, got.reason) == (False, "central_act")


@pytest.mark.parametrize("node", OFFLINE_NODES)
def test_an_admin_command_on_a_none_type_is_a_central_act_not_online_only(node: NodeKind) -> None:
    # The central check comes before the class check: a none type with an admin word says so.
    got = capture_allowed("cost.CostSnapshot", "ImportCostSnapshot", node=node)
    assert (got.allowed, got.reason) == (False, "central_act")


@pytest.mark.parametrize("word", CENTRAL)
def test_every_central_word_is_refused_before_the_class_is_read(word: str) -> None:
    tag = stand_in(
        name="engineering",
        record_types=frozenset({"engineering.Tag"}),
        command_words={"SignOffTag": word, "CreateTag": "user"},
    )
    with use_modules([tag]):
        central = capture_allowed("engineering.Tag", "SignOffTag", node="site")
        user = capture_allowed("engineering.Tag", "CreateTag", node="site")
    assert (central.allowed, central.reason) == (False, "central_act")  # engineering.Tag is full
    assert (user.allowed, user.reason) == (True, "full")


@pytest.mark.parametrize("node", OFFLINE_NODES)
def test_a_generic_command_on_a_none_type_is_online_only(node: NodeKind) -> None:
    got = capture_allowed("cost.CostCode", "AddLink", node=node)
    assert (got.allowed, got.reason) == (False, "online_only")
    got = capture_allowed("documents.ReviewCycle", "SetPsetValues", node=node)
    assert (got.allowed, got.reason) == (False, "online_only")


@pytest.mark.parametrize("node", OFFLINE_NODES)
def test_a_full_type_allows_a_generic_command(node: NodeKind) -> None:
    for command in GENERIC:
        got = capture_allowed("engineering.Tag", command, node=node)
        assert (got.allowed, got.reason) == (True, "full")
    assert capture_allowed("core.Record", "AddLink", node=node).reason == "full"


@pytest.mark.parametrize("node", OFFLINE_NODES)
def test_a_draft_only_type_allows_its_listed_drafting_commands(node: NodeKind) -> None:
    for record_type, commands in SECTION_4_DRAFTS.items():
        for command in commands:
            got = capture_allowed(record_type, command, node=node)
            assert (got.allowed, got.reason) == (True, "draft"), (record_type, command)


@pytest.mark.parametrize("node", OFFLINE_NODES)
def test_a_draft_only_type_refuses_what_it_does_not_list(node: NodeKind) -> None:
    for command in GENERIC:
        got = capture_allowed("documents.Revision", command, node=node)
        assert (got.allowed, got.reason) == (False, "not_drafting"), command
    # a drafting command of another type is not a drafting command of this one
    got = capture_allowed("documents.Rendition", "CreateRevision", node=node)
    assert (got.allowed, got.reason) == (False, "not_drafting")


def test_a_command_with_no_declared_word_follows_the_class_of_its_type() -> None:
    assert capture_allowed("documents.Revision", "NoSuchCommand", node="site").reason == (
        "not_drafting"
    )
    assert capture_allowed("cost.CostCode", "NoSuchCommand", node="site").reason == "online_only"
    assert capture_allowed("engineering.Tag", "NoSuchCommand", node="site").reason == "full"


def test_a_draft_only_type_with_a_stand_in_listing_allows_only_that_command() -> None:
    spec = stand_in(
        name="documents",
        record_types=frozenset({"documents.Document"}),
        command_words={"RegisterDocument": "user", "OtherDraft": "user"},
        offline_drafts={"documents.Document": frozenset({"RegisterDocument"})},
    )
    with use_modules([spec]):
        assert capture_allowed("documents.Document", "RegisterDocument", node="site").reason == (
            "draft"
        )
        assert capture_allowed("documents.Document", "OtherDraft", node="site").reason == (
            "not_drafting"
        )


def test_require_capture_allowed_returns_none_when_allowed() -> None:
    assert require_capture_allowed("engineering.Tag", "AddLink", node="device") is None
    assert require_capture_allowed("cost.CostCode", "AddLink", node="authority") is None
    assert require_capture_allowed("documents.Revision", "CreateRevision", node="site") is None


def test_require_capture_allowed_raises_online_only_with_the_reason_in_the_text() -> None:
    with pytest.raises(OnlineOnlyError) as caught:
        require_capture_allowed("cost.CostCode", "AddLink", node="site")
    text = str(caught.value)
    assert "cost.CostCode" in text and "AddLink" in text and "site" in text
    assert "online_only" in text
    with pytest.raises(OnlineOnlyError, match="central_act"):
        require_capture_allowed("documents.Revision", "IssueRevision", node="device")


def test_offline_class_reads_the_generated_table_and_an_unknown_type_is_none() -> None:
    assert offline_class("core.Record") == "full"
    assert offline_class("documents.Revision") == "draft_only"
    assert offline_class("legacy.LoadRun") == "none"
    assert offline_class("no.Such") == "none"
    assert {rt: offline_class(rt) for rt in OFFLINE_CLASSES} == dict(OFFLINE_CLASSES)


def test_stream_class_reads_the_stream_table_and_an_unknown_stream_is_none() -> None:
    assert stream_class("core.ActivityPost") == "full"
    assert stream_class("core.Thread") == "full"
    assert stream_class("core.Account") == "none"
    assert stream_class("core.InboundDelivery") == "none"
    assert stream_class("core.Nope") == "none"
    assert stream_class("") == "none"


def test_node_kind_is_authority_when_unset_or_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    assert node_kind() == "authority"
    monkeypatch.setenv(offline.NODE_KIND_VARIABLE, "")
    assert node_kind() == "authority"
    monkeypatch.setenv(offline.NODE_KIND_VARIABLE, "   ")
    assert node_kind() == "authority"


@pytest.mark.parametrize("value", ["authority", "site", "device"])
def test_node_kind_reads_each_kind(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(offline.NODE_KIND_VARIABLE, f" {value} ")
    assert node_kind() == value


@pytest.mark.parametrize("value", ["moon", "Site", "AUTHORITY"])
def test_a_bad_node_kind_is_a_value_error_naming_the_variable(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(offline.NODE_KIND_VARIABLE, value)
    with pytest.raises(ValueError, match="TL_NODE_KIND must be one of authority, site, device"):
        node_kind()


def test_is_authority_is_true_only_on_an_authority_node(monkeypatch: pytest.MonkeyPatch) -> None:
    assert is_authority("project:P1")
    monkeypatch.setenv(offline.NODE_KIND_VARIABLE, "site")
    assert not is_authority("project:P1")
    monkeypatch.setenv(offline.NODE_KIND_VARIABLE, "device")
    assert not is_authority("company")


def test_require_node_built_passes_on_an_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    assert require_node_built() is None
    monkeypatch.setenv(offline.NODE_KIND_VARIABLE, "authority")
    assert require_node_built() is None


@pytest.mark.parametrize("value", ["site", "device"])
def test_require_node_built_refuses_a_replica_kind(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(offline.NODE_KIND_VARIABLE, value)
    with pytest.raises(NodeKindNotBuiltError, match="offline replicas arrive in Phase 3"):
        require_node_built()


def test_require_node_built_refuses_a_bad_kind_with_a_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(offline.NODE_KIND_VARIABLE, "moon")
    with pytest.raises(ValueError, match="TL_NODE_KIND"):
        require_node_built()


def test_the_record_type_rows_follow_the_table_and_the_modules() -> None:
    rows = record_type_rows()
    assert [r.record_type for r in rows] == sorted(OFFLINE_CLASSES)
    assert {r.record_type: r.offline for r in rows} == dict(OFFLINE_CLASSES)
    by_type = {r.record_type: r for r in rows}
    assert by_type["engineering.Tag"].offline == "full"
    assert by_type["engineering.Tag"].drafting_commands == []
    assert by_type["documents.Revision"].drafting_commands == ["CreateRevision", "VoidRevision"]
    assert by_type["documents.Revision"].module == "documents"
    assert all(r.drafting_commands == [] for r in rows if r.offline != "draft_only")
    assert {r.record_type: frozenset(r.drafting_commands) for r in rows if r.drafting_commands} == (
        SECTION_4_DRAFTS
    )

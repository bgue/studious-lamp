"""Acceptance for OC-S2 (P2-W0): the offline capture hook, the module-load checks and the node kind.
Exit 0, one ``PASS <check>`` line per check, the decision table at the end. No database.

Run: ``uv run python dev/accept/P2-W0/OC-S2.py``.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from tl_core import offline
from tl_core.extypes import provider as ext_provider
from tl_core.extypes import registry as ext_registry
from tl_core.extypes.compile import compile_type, to_package_doc
from tl_core.extypes.loader import LoadedType
from tl_core.extypes.names import parse_type_ref
from tl_core.extypes.types import TypeRegistration, TypeView
from tl_core.modules import ModuleLoadError, ModuleSpec, check_offline, load_modules, use_modules
from tl_schema.generated.offline_classes import OFFLINE_CLASSES

ROOT = Path(__file__).resolve().parents[3]
LIFT = ROOT / "schema" / "fixtures" / "types" / "co.acme" / "LiftPlan" / "1.0.0"
GENERIC = offline.GENERIC_CAPTURE_COMMANDS
NODES: tuple[offline.NodeKind, ...] = ("authority", "site", "device")
passed = 0


def ok(name: str) -> None:
    global passed
    passed += 1
    print(f"PASS {name}")


def check(condition: bool, name: str, detail: object = "") -> None:
    if not condition:
        raise SystemExit(f"FAIL {name}: {detail}")
    ok(name)


def raises(exc: type[Exception], fn: Callable[[], Any], needles: tuple[str, ...] = ()) -> str:
    try:
        fn()
    except exc as caught:
        text = str(caught)
        missing = [n for n in needles if n not in text]
        if missing:
            raise SystemExit(f"FAIL message {text!r} lacks {missing}") from None
        return text
    raise SystemExit(f"FAIL {exc.__name__} not raised")


@contextmanager
def env(value: str | None) -> Iterator[None]:
    before = os.environ.get(offline.NODE_KIND_VARIABLE)
    if value is None:
        os.environ.pop(offline.NODE_KIND_VARIABLE, None)
    else:
        os.environ[offline.NODE_KIND_VARIABLE] = value
    try:
        yield
    finally:
        if before is None:
            os.environ.pop(offline.NODE_KIND_VARIABLE, None)
        else:
            os.environ[offline.NODE_KIND_VARIABLE] = before


def stand_in(**kw: Any) -> ModuleSpec:
    return ModuleSpec(projectors=lambda: [], **kw)  # type: ignore[arg-type]


# --- the table of section 4, written out here, not read from the modules ------------------------

SECTION_4_DRAFTS: dict[str, frozenset[str]] = {
    "documents.Document": frozenset({"RegisterDocument", "UpdateDocument"}),
    "documents.Revision": frozenset({"CreateRevision", "VoidRevision"}),
    "documents.Rendition": frozenset({"AttachRendition"}),
    "documents.Transmittal": frozenset({"CreateTransmittal", "VoidTransmittal"}),
    "correspondence.Correspondence": frozenset(
        {"DraftCorrespondence", "UpdateCorrespondence", "VoidDraft"}
    ),
    "correspondence.TechnicalItem": frozenset({"RaiseTechnical", "UpdateTechnical"}),
}


def module_drafts() -> dict[str, frozenset[str]]:
    found: dict[str, frozenset[str]] = {}
    for spec in load_modules():
        found.update(spec.offline_drafts)
    return found


def oracle(rt: str, command: str, word: str | None, node: str) -> tuple[bool, str]:
    """The rule of section 5 item 3 written independently of ``offline.py``."""
    if node == "authority":
        return True, "authority"
    cls = OFFLINE_CLASSES.get(rt)
    if cls is None:
        return False, "unknown_type"
    if word in ("controller", "admin", "company"):
        return False, "central_act"
    if cls == "none":
        return False, "online_only"
    if cls == "full":
        return True, "full"
    if command in SECTION_4_DRAFTS.get(rt, frozenset()):
        return True, "draft"
    return False, "not_drafting"


def decision_table() -> None:
    words: dict[str, dict[str, str]] = {s.name: dict(s.command_words) for s in load_modules()}
    rows: list[tuple[str, str, str | None, str, bool, str]] = []
    for rt in OFFLINE_CLASSES:
        module = rt.split(".")[0]
        commands = {**words.get(module, {}), **dict.fromkeys(GENERIC)}
        for command, word in commands.items():
            for node in NODES:
                d = offline.capture_allowed(rt, command, node=node)
                want = oracle(rt, command, word, node)
                check_quiet((d.allowed, d.reason) == want, f"{node} {rt} {command}", (d, want))
                rows.append((node, rt, word, command, d.allowed, d.reason))
    ok(f"capture_allowed equals the section 5 rule on {len(rows)} (node, type, command) rows")
    for node in NODES:
        counts = Counter(r[5] for r in rows if r[0] == node)
        allowed = sum(1 for r in rows if r[0] == node and r[4])
        refused = sum(1 for r in rows if r[0] == node and not r[4])
        print(
            f"  {node:9s} allowed {allowed:4d} refused {refused:4d}  {dict(sorted(counts.items()))}"
        )
    samples = [
        ("site", "documents.Revision", "CreateRevision"),
        ("site", "documents.Revision", "IssueRevision"),
        ("device", "documents.Revision", "AddLink"),
        ("device", "cost.CostCode", "AddLink"),
        ("site", "engineering.Tag", "SetPsetValues"),
        ("authority", "cost.CostCode", "AddLink"),
    ]
    print("  sample rows (node, type, command -> allowed, reason):")
    for node, rt, command in samples:
        d = offline.capture_allowed(rt, command, node=node)  # type: ignore[arg-type]
        print(f"    {node:9s} {rt:32s} {command:22s} -> {d.allowed!s:5s} {d.reason}")


def check_quiet(condition: bool, name: str, detail: object = "") -> None:
    if not condition:
        raise SystemExit(f"FAIL {name}: {detail}")


def main() -> int:
    # --- the drafting entries -------------------------------------------------------------------
    drafts = module_drafts()
    check(drafts == SECTION_4_DRAFTS, "offline_drafts of the modules equal section 4", drafts)
    check(
        all(
            not s.offline_drafts
            for s in load_modules()
            if s.name not in ("documents", "correspondence")
        ),
        "the five other modules declare no drafting commands",
    )
    check(len(load_modules()) == 7, "seven modules load and pass the offline load checks")

    # --- the decision table ---------------------------------------------------------------------
    decision_table()
    check(
        offline.capture_allowed("x.Unknown", "Anything", node="authority")
        == offline.OfflineDecision(allowed=True, reason="authority"),
        "authority allows everything, an unknown type included",
    )
    check(
        offline.capture_allowed("x.Unknown", "Anything", node="site").reason == "unknown_type",
        "an unknown type is refused on a site",
    )
    check(
        offline.capture_allowed("documents.Revision", "IssueRevision", node="device").reason
        == "central_act",
        "controller command on a draft_only type is central_act",
    )
    # a `full` type with a controller / admin / company command: refused before the class is read
    for word in ("controller", "admin", "company"):
        tag = stand_in(
            name="engineering",
            record_types=frozenset({"engineering.Tag"}),
            command_words={"SignOffTag": word, "CreateTag": "user"},
        )
        with use_modules([tag]):
            d = offline.capture_allowed("engineering.Tag", "SignOffTag", node="site")
            u = offline.capture_allowed("engineering.Tag", "CreateTag", node="site")
        check(
            (d.allowed, d.reason) == (False, "central_act")
            and (u.allowed, u.reason) == (True, "full"),
            f"{word} refused before the class is read (full type); user on the same type allowed",
        )
    d = offline.capture_allowed("documents.Revision", "AddLink", node="site")
    check(
        (d.allowed, d.reason) == (False, "not_drafting"),
        "generic command on draft_only: not_drafting",
    )

    # --- require_capture_allowed and its API row ------------------------------------------------
    offline.require_capture_allowed("engineering.Tag", "AddLink", node="device")
    offline.require_capture_allowed("cost.CostCode", "AddLink", node="authority")
    text = raises(
        offline.OnlineOnlyError,
        lambda: offline.require_capture_allowed("cost.CostCode", "AddLink", node="site"),
        ("cost.CostCode", "AddLink"),
    )
    from tl_api.errors import spec_for

    row = spec_for(offline.OnlineOnlyError(text))
    check(
        row is not None and (row.error, row.status) == ("online_only", 409),
        "OnlineOnlyError is 409 online_only",
    )
    row = spec_for(offline.NodeKindNotBuiltError("x"))
    check(row is not None and row.status == 503, "NodeKindNotBuiltError has an API row", row)

    # --- the three module-load errors -----------------------------------------------------------
    msg = raises(
        ModuleLoadError,
        lambda: check_offline(stand_in(name="zzz", record_types=frozenset({"zzz.Thing"}))),
        ("zzz", "zzz.Thing", "no offline class"),
    )
    check(True, "load error 1, undeclared type: " + msg)
    msg = raises(
        ModuleLoadError,
        lambda: check_offline(
            stand_in(
                name="engineering",
                record_types=frozenset({"engineering.Tag"}),
                command_words={"CreateTag": "user"},
                offline_drafts={"engineering.Tag": frozenset({"CreateTag"})},
            )
        ),
        ("engineering", "engineering.Tag", "'full'"),
    )
    check(True, "load error 2, drafting entry on a full type: " + msg)
    msg = raises(
        ModuleLoadError,
        lambda: check_offline(
            stand_in(
                name="cost",
                record_types=frozenset({"cost.CostCode"}),
                command_words={"X": "user"},
                offline_drafts={"cost.CostCode": frozenset({"X"})},
            )
        ),
        ("cost", "cost.CostCode", "'none'"),
    )
    check(True, "load error 2, drafting entry on a none type: " + msg)
    for word in ("controller", "admin", "company"):
        msg = raises(
            ModuleLoadError,
            lambda word=word: check_offline(
                stand_in(
                    name="documents",
                    record_types=frozenset({"documents.Document"}),
                    command_words={"RegisterDocument": word},
                    offline_drafts={"documents.Document": frozenset({"RegisterDocument"})},
                )
            ),
            ("documents", "RegisterDocument", repr(word)),
        )
        check(True, f"load error 3, {word} command listed: " + msg)
    raises(
        ModuleLoadError,
        lambda: check_offline(
            stand_in(
                name="documents",
                record_types=frozenset({"documents.Document"}),
                offline_drafts={"documents.Document": frozenset({"RegisterDocument"})},
            )
        ),
        ("RegisterDocument", "command_words"),
    )
    ok("a drafting command missing from command_words is refused")
    check_offline(
        stand_in(
            name="documents",
            record_types=frozenset({"documents.Document"}),
            command_words={"RegisterDocument": "user"},
            offline_drafts={"documents.Document": frozenset({"RegisterDocument"})},
        )
    )
    ok("a consistent stand-in passes the load check")

    # --- extension types ------------------------------------------------------------------------
    coords = parse_type_ref("co.acme.LiftPlan@1.0.0")
    with tempfile.TemporaryDirectory() as tmp:

        def package(annotation: str | None) -> Path:
            target = Path(tmp) / (annotation or "missing").replace(" ", "_").replace(":", "_")
            shutil.copytree(LIFT, target)
            if annotation is not None:
                path = target / "type.yaml"
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        "      tl:storage_mode: object-backed\n",
                        f"      tl:storage_mode: object-backed\n      tl:offline: {annotation}\n",
                    ),
                    encoding="utf-8",
                )
            return target

        compiled, issues = compile_type(package("draft_only"), coords, lint=False)
        check(
            compiled is not None and compiled.offline == "draft_only",
            "tl:offline: draft_only compiles",
            issues,
        )
        missing, issues = compile_type(package(None), coords, lint=False)
        check(missing is not None and missing.offline == "none", "a missing key is none", issues)
        bad, issues = compile_type(package("sometimes"), coords, lint=False)
        check(
            bad is None
            and issues
            and issues[0].kind == "compile"
            and "tl:offline" in issues[0].detail,
            "a bad value is a compile issue",
            issues,
        )
        assert compiled is not None and missing is not None
        hash_a, hash_b = compiled.schema_hash(), missing.schema_hash()
        check(hash_a == hash_b, "tl:offline does not change the schema hash")

        # offline_class reads what the attached source holds, with no IO of its own
        def registration(c: Any) -> TypeRegistration:
            return TypeRegistration(
                namespace=c.namespace,
                name=c.name,
                version=c.version,
                type_ref=c.type_ref,
                location_uri="file:///nowhere",
                content_hash="0" * 64,
                owner="user:x",
                status="active",
                storage_mode="object-backed",
                index_fields=[],
                schema_hash=c.schema_hash(),
            )

        class Loader:
            def __init__(self, c: Any) -> None:
                self.c = c

            def load(self, reg: TypeRegistration) -> LoadedType:
                return LoadedType(reg, self.c, to_package_doc(self.c))

            def verify(self, reg: TypeRegistration) -> None:
                return None

        class Uow:
            def __enter__(self) -> Uow:
                return self

            def __exit__(self, *a: object) -> None:
                return None

            def conn(self) -> None:
                return None

        def source_for(c: Any) -> ext_provider.LedgerExtensionSource:
            reg = registration(c)
            ext_registry.usable_types = lambda conn: [TypeView(registration=reg, seq=1)]  # type: ignore[assignment]
            ext_provider.settings_link.refresh = lambda views, verify: None  # type: ignore[assignment]
            src = ext_provider.LedgerExtensionSource(lambda readonly=False: Uow(), loader=Loader(c))  # type: ignore[arg-type]
            src.documents()
            return src

        ext_provider._attached = None
        check(
            offline.offline_class("co.acme.LiftPlan") == "none",
            "an extension type nobody attached is none",
        )
        ext_provider._attached = source_for(compiled)
        check(
            offline.offline_class("co.acme.LiftPlan") == "draft_only",
            "offline_class returns the registered type's class",
        )
        d = offline.capture_allowed("co.acme.LiftPlan", "CreateRecord", node="site")
        check(
            (d.allowed, d.reason) == (False, "not_drafting"),
            "a draft_only extension type lists no drafting command",
        )
        ext_provider._attached = source_for(missing)
        check(
            offline.offline_class("co.acme.LiftPlan") == "none",
            "a registered type without the key is none",
        )
        d = offline.capture_allowed("co.acme.LiftPlan", "CreateRecord", node="site")
        check(
            (d.allowed, d.reason) == (False, "online_only"),
            "a registered none extension type is online_only, not unknown",
        )
        d = offline.capture_allowed("co.acme.Other", "CreateRecord", node="site")
        check(d.reason == "unknown_type", "an unregistered extension type is unknown_type")
        ext_provider._attached = None

    # --- node kind ------------------------------------------------------------------------------
    with env(None):
        check(offline.node_kind() == "authority", "node_kind default is authority")
        offline.require_node_built()
        check(offline.is_authority("project:P1"), "is_authority on an authority node")
    with env(""):
        check(offline.node_kind() == "authority", "an empty TL_NODE_KIND is authority")
    with env("device"):
        check(offline.node_kind() == "device", "node_kind reads device")
        check(not offline.is_authority("project:P1"), "is_authority is false on a device")
        raises(
            offline.NodeKindNotBuiltError,
            offline.require_node_built,
            ("offline replicas arrive in Phase 3",),
        )
        ok("require_node_built refuses device")
    with env("site"):
        raises(offline.NodeKindNotBuiltError, offline.require_node_built)
        ok("require_node_built refuses site")
    with env("moon"):
        raises(ValueError, offline.node_kind, (offline.NODE_KIND_VARIABLE,))
        ok("a bad TL_NODE_KIND is a ValueError naming the variable")

    # --- streams --------------------------------------------------------------------------------
    check(
        offline.stream_class("core.ActivityPost") == "full",
        "stream_class(core.ActivityPost) is full",
    )
    check(offline.stream_class("core.Account") == "none", "stream_class(core.Account) is none")
    check(offline.stream_class("core.Nope") == "none", "an unknown stream is none")
    check(
        offline.offline_class("core.Record") == "full"
        and offline.offline_class("no.Such") == "none",
        "offline_class: generated table, unknown is none",
    )

    print(f"{passed} PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

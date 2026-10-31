"""Acceptance for W0-B2 (P2-W0): load and publish targets found by entry point. SQLite, exit 0,
one ``PASS <check>`` line per check.

Run: ``uv run python dev/accept/P2-W0/W0-B2.py``.

The expectations of the Phase 1 demos are the ones used here: the tag list loads 11 tags (P1-I1's
``created=11``), a document register loads and reconciles with no mismatch (P1-I8 clause 5), and a
derived document publishes 3 tags or 2 documents with one ``derived_from`` link per record and
rolls back by voiding (``test_derivation_publish``).
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import types
from collections.abc import Callable
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.db import as_target, create_schema, open_uow
from tl_cli.main import app
from tl_core.derivation.registry import use_extractors
from tl_core.derivation.testing import make_extractors
from tl_core.modules import ModuleLoadError
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_mod_documents.derivation.publish import (
    CompensatePublication,
    PublishDerivedDocuments,
    PublishDerivedTags,
    handle_compensate_publication,
    handle_publish_derived_documents,
    handle_publish_derived_tags,
)
from tl_mod_documents.derivation.publish_targets import (
    PUBLISH_ENTRY_POINT,
    PublishTargetLoadError,
    load_publish_targets,
    publish_target_for,
    use_publish_targets,
)
from tl_mod_documents.derivation.store import use_files
from tl_mod_documents.errors import PublishRefusedError
from tl_mod_documents.testing import BASE, DocumentsWorld
from tl_mod_legacy.errors import LoadRefusedError
from tl_mod_legacy.model import LoaderDef, use_loaders
from tl_mod_legacy.targets import (
    LOAD_TARGET_ENTRY_POINT,
    TargetLoadError,
    installed_targets,
    load_targets,
    mapping_target,
    target_for,
    use_targets,
)
from tl_mod_legacy.testing import LegacyWorld
from typer.testing import CliRunner

REPO = Path(__file__).resolve().parents[3]
os.environ.pop("TL_SCHEMA_DIR", None)
os.environ.setdefault("TL_ENV", "dev")
FIXTURES = REPO / "schema" / "fixtures"
PASSWORD = "correct horse battery"
TAGS = [
    ("47-FV-1001", "Feed", "CV", "4"),
    ("47-HV-1002", "Return", "HV", "6"),
    ("47-PSV-2001", "Vent", "PSV", "2"),
]
DOC_SCHEMA = {
    "type": "object",
    "required": ["number", "title"],
    "properties": {
        "number": {"type": "string"},
        "title": {"type": "string"},
        "discipline": {"type": "string"},
    },
}
DOC_MAPPING = {
    "target": "documents",
    "key_column": "number",
    "columns": [
        {"column": "number", "to": "number"},
        {"column": "title", "to": "title"},
        {"column": "discipline", "to": "discipline"},
    ],
}
logging.disable(logging.WARNING)  # the registries log a plugin that cannot be loaded; expected here
failures: list[str] = []


def passed(name: str) -> None:
    print(f"PASS {name}")


def expect(condition: bool, what: str) -> None:
    if condition:
        passed(what)
    else:
        failures.append(what)
        print(f"FAIL {what}")


def expect_raises(
    exc: type[BaseException], fn: Callable[[], object], what: str, *words: str
) -> None:
    try:
        fn()
    except exc as raised:
        missing = [w for w in words if w not in str(raised)]
        expect(not missing, f"{what} (message names {', '.join(words) or 'nothing'})")
        if missing:
            print(f"  message was: {raised}")
    except BaseException as other:  # noqa: BLE001
        failures.append(f"{what}: raised {type(other).__name__}, wanted {exc.__name__}")
        print(f"FAIL {what}")
    else:
        failures.append(f"{what}: did not raise")
        print(f"FAIL {what}")


# --- injected plugins --------------------------------------------------------------------------

plugins = types.ModuleType("w0b2_plugins")
sys.modules["w0b2_plugins"] = plugins


def _make(name: str) -> Callable[[], Any]:
    def factory() -> Any:
        return mapping_target(
            name,
            module="plugins",
            record_type="documents.Transmittal",
            key_column="key",
            columns={"title": "title"},
        )

    return factory


plugins.again = _make("tags")  # type: ignore[attr-defined]
plugins.fine = _make("fine")  # type: ignore[attr-defined]
plugins.shouty = _make("shouty")  # type: ignore[attr-defined]


def _publish_again() -> Any:
    from tl_mod_documents.derivation.publish import tags_target

    return tags_target()


plugins.publish_again = _publish_again  # type: ignore[attr-defined]


def points(group: str, *pairs: tuple[str, str]) -> list[EntryPoint]:
    return [EntryPoint(name=n, value=v, group=group) for n, v in pairs]


# --- the load registry -------------------------------------------------------------------------


def load_registry() -> None:
    found = installed_targets()
    expect(
        [(t.kind, t.module, t.scope) for t in found.values()]
        == [("documents", "legacy", "project"), ("tags", "legacy", "project")],
        "both built-in load targets are listed with module and scope",
    )
    expect(list(load_targets()) == ["documents", "tags"], "load_targets() reads the group, sorted")
    builtin = [
        ("tags", "tl_mod_legacy.targets:tags_target"),
        ("documents", "tl_mod_legacy.targets:documents_target"),
    ]
    expect(
        sorted(load_targets(points(LOAD_TARGET_ENTRY_POINT, *builtin))) == ["documents", "tags"],
        "injected entry points are read instead of the installed ones",
    )
    expect_raises(
        TargetLoadError,
        lambda: load_targets(
            points(
                LOAD_TARGET_ENTRY_POINT,
                ("tags", "tl_mod_legacy.targets:tags_target"),
                ("tags", "w0b2_plugins:again"),
            )
        ),
        "a duplicate load target name raises",
        LOAD_TARGET_ENTRY_POINT,
        "'tags'",
        "twice",
    )
    expect_raises(
        TargetLoadError,
        lambda: load_targets(points(LOAD_TARGET_ENTRY_POINT, ("broken", "w0b2_missing:thing"))),
        "a load target that fails to import raises",
        LOAD_TARGET_ENTRY_POINT,
        "'broken'",
        "cannot be loaded",
    )
    expect_raises(
        TargetLoadError,
        lambda: load_targets(
            points(LOAD_TARGET_ENTRY_POINT, ("Shouty-Name", "w0b2_plugins:shouty"))
        ),
        "a load target with a bad name raises",
        LOAD_TARGET_ENTRY_POINT,
        "'Shouty-Name'",
        "^[a-z][a-z0-9_]*$",
    )
    expect(
        issubclass(TargetLoadError, ModuleLoadError), "a load registry error is a ModuleLoadError"
    )
    expect_raises(
        LoadRefusedError,
        lambda: target_for("nope"),
        "an unknown load target is refused and names the known ones",
        "'nope'",
        "documents, tags",
    )


# --- the publish registry ----------------------------------------------------------------------


def publish_registry() -> None:
    found = load_publish_targets()
    expect(
        [(t.name, t.module, t.record_type) for t in found.values()]
        == [
            ("documents", "documents", "documents.Document"),
            ("tags", "documents", "engineering.Tag"),
        ],
        "both built-in publish targets are found by their group",
    )
    expect_raises(
        PublishTargetLoadError,
        lambda: load_publish_targets(
            points(
                PUBLISH_ENTRY_POINT,
                ("tags", "tl_mod_documents.derivation.publish:tags_target"),
                ("tags", "w0b2_plugins:publish_again"),
            )
        ),
        "a duplicate publish target name raises",
        PUBLISH_ENTRY_POINT,
        "'tags'",
        "twice",
    )
    expect_raises(
        PublishTargetLoadError,
        lambda: load_publish_targets(points(PUBLISH_ENTRY_POINT, ("broken", "w0b2_missing:thing"))),
        "a publish target that fails to import raises",
        PUBLISH_ENTRY_POINT,
        "'broken'",
    )
    expect_raises(
        PublishTargetLoadError,
        lambda: load_publish_targets(
            points(PUBLISH_ENTRY_POINT, ("Bad Name", "w0b2_plugins:fine"))
        ),
        "a publish target with a bad name raises",
        PUBLISH_ENTRY_POINT,
        "^[a-z][a-z0-9_]*$",
    )
    expect_raises(
        PublishRefusedError,
        lambda: publish_target_for("nope"),
        "an unknown publish target is refused and names the known ones",
        "'nope'",
        "documents, tags",
    )


# --- the command line and the loads ------------------------------------------------------------


def cli(env: dict[str, str], *args: str, ok: bool = True, stdin: str | None = None) -> str:
    result = CliRunner().invoke(app, list(args), env=env, input=stdin)
    if (result.exit_code == 0) != ok:
        raise AssertionError(f"tl {' '.join(args)}: exit {result.exit_code}\n{result.output}")
    return result.output


def loads_through_the_cli(work: Path) -> None:
    env = {
        "TL_DB": str(work / "cli.db"),
        "TL_ENV": "dev",
        "TL_OBJECT_ROOT": str(work / "cli-objects"),
        "TL_SESSION_FILE": str(work / "session.json"),
        "TL_LAKE_DIR": str(work / "lake"),
    }
    cli(env, "init")
    cli(env, "admin", "bootstrap", "--username", "root", "--password-stdin", stdin=PASSWORD)
    cli(env, "login", "root", "--password-stdin", stdin=PASSWORD)
    LegacyWorld(as_target(env["TL_DB"]), work / "unused").load_standards()
    expect(
        cli(env, "load", "targets") == "documents  legacy  project\ntags  legacy  project\n",
        "tl load targets prints the two built-ins, sorted, one line each",
    )
    project = ["--project", "P123"]
    tag_file = str(REPO / "dev" / "seed" / "legacy" / "instrument-index.csv")
    opened = cli(env, "load", "open", tag_file, *project, "--loader", "instrument-index")
    run = opened.split()[1]
    for stage in ("extract", "profile", "plan"):
        cli(env, "load", stage, run, *project)
    done = cli(env, "load", "load", run, *project)
    expect(" created 11 " in done, "tl load open through tags creates the 11 tags of P1-I1")
    expect(
        "mismatches 0" in cli(env, "load", "reconcile", run, *project),
        "the tag load reconciles with no mismatch",
    )
    sys.path.insert(0, str(REPO / "dev" / "demos"))
    from p1_i8_demo import registers  # the three-document register of P1-I8 clause 5

    registers(work / "registers")
    doc_file = str(work / "registers" / "register.csv")
    opened = cli(env, "load", "open", doc_file, *project, "--loader", "dms-register")
    run = opened.split()[1]
    for stage in ("extract", "profile", "plan", "load"):
        out = cli(env, "load", stage, run, *project)
    expect(
        " created 3 existing 0 invalid 0 " in out,
        "tl load open through documents creates the 3 documents of P1-I8",
    )
    expect(
        "mismatches 0" in cli(env, "load", "reconcile", run, *project),
        "the document load reconciles with no mismatch",
    )
    # scope: a company stand-in target needs --company; a project target refuses it
    stand_in = mapping_target(
        "stand_in",
        module="plugins",
        record_type="engineering.TagClass",
        key_column="key",
        columns={"title": "title"},
        scope="company",
    )
    company_loader = LoaderDef(
        name="co-loader",
        system="plugins",
        table="things",
        target="stand_in",
        description="A company stand-in.",
        mapping_text="{}",
        file_types=("csv",),
    )
    csv_path = work / "things.csv"
    csv_path.write_text("key,title\nTC:ONE,One\nTC:TWO,Two\n", encoding="utf-8")
    with (
        use_targets({**installed_targets(), "stand_in": stand_in}),
        use_loaders({"co-loader": company_loader}),
    ):
        listed = cli(env, "load", "targets")
        expect("stand_in  plugins  company\n" in listed, "tl load targets lists a company target")
        refused = cli(
            env, "load", "open", str(csv_path), *project, "--loader", "co-loader", ok=False
        )
        expect("--company" in refused, "a company target refuses a project run and names --company")
        opened = cli(env, "load", "open", str(csv_path), "--company", "--loader", "co-loader")
        expect(
            opened.startswith("opened plugins/things#1 "), "a company target opens with --company"
        )
        scope = _scalar(
            env["TL_DB"], "SELECT scope FROM cur_core_record WHERE key = 'plugins/things#1'"
        )
        expect(scope == "company", "the company run is in the company scope")
    with use_loaders({"tag-loader": _tag_loader()}):
        refused = cli(
            env,
            "load",
            "open",
            tag_file,
            "--company",
            "--loader",
            "tag-loader",
            ok=False,
        )
        expect("--project" in refused, "a project target refuses --company and names --project")
        both = cli(
            env, "load", "open", tag_file, *project, "--company", "--loader", "tag-loader", ok=False
        )
        expect("not both" in both, "giving --project and --company together is refused")


def _tag_loader() -> LoaderDef:
    from tl_mod_legacy.testing import tag_loader

    return tag_loader("tag-loader")


def _scalar(db: str, sql: str) -> Any:
    with open_uow(as_target(db), readonly=True) as uow:
        return uow.conn().execute(text(sql)).scalar_one()


def mapping_form(work: Path) -> None:
    db = as_target(str(work / "mapping.db"))
    create_schema(db)
    world = LegacyWorld(db, work / "mapping-objects")
    target = mapping_target(
        "things",
        module="plugins",
        record_type="documents.Transmittal",
        key_column="key",
        columns={"title": "title", "note": "description"},
    )
    loader = LoaderDef(
        name="things",
        system="plugins",
        table="things",
        target="things",
        description="Things from a declarative mapping.",
        mapping_text="{}",
        file_types=("csv",),
    )
    data = b"key,title,note\nTHING-1,First,a note\nTHING-2,Second,\n"
    with use_targets({**installed_targets(), "things": target}), use_loaders({"things": loader}):
        run = world.open("things", "things.csv", data)
        world.service.extract("project:P123", run.id, actor="user:admin")
        world.service.profile("project:P123", run.id, actor="user:admin")
        planned, plan = world.service.plan("project:P123", run.id, actor="user:admin")
        expect(
            (planned.plan_new, planned.plan_existing, planned.plan_invalid) == (2, 0, 0),
            "a mapping-form target plans two new rows",
        )
        outcome = world.service.load("project:P123", run.id, actor="user:admin", expect_new=2)
        expect(outcome.created == 2, "a mapping-form target loads two rows")
        keys = world.rows(
            "SELECT key, title FROM cur_core_record WHERE type = 'documents.Transmittal' "
            "ORDER BY key"
        )
        expect(
            [(k["key"], k["title"]) for k in keys] == [("THING-1", "First"), ("THING-2", "Second")],
            "the rows are records of the mapped type with the mapped titles",
        )
        report = world.service.reconcile("project:P123", run.id, actor="user:admin")[1]
        expect(report["mismatches"] == 0, "the mapping-form load reconciles with no mismatch")
        reversed_ = world.service.compensate(
            "project:P123", run.id, actor="user:admin", reason="acceptance"
        )
        expect(reversed_.reversed == 2, "compensation voids exactly the two records the run made")
        voided = world.scalar(
            "SELECT COUNT(*) FROM cur_core_record WHERE type = 'documents.Transmittal' AND voided"
        )
        expect(bool(voided == 2), "both records are voided and nothing else changed")


# --- publishing --------------------------------------------------------------------------------


def publishes(work: Path) -> None:
    db = as_target(str(work / "publish.db"))
    create_schema(db)
    world = DocumentsWorld(db, work / "publish-objects")
    with (
        use_provider(DirectorySchemaProvider(FIXTURES)),
        use_extractors(make_extractors()),
        use_files(world.files),
    ):
        world.load_standards()
        world.register("ISD-001")
        world.create_revision("ISD-001")
        world.attach("ISD-001", "A")
        world.register_schema()
        derived = world.valid_derived(TAGS)
        with open_uow(db) as uow:
            handle_publish_derived_tags(
                uow,
                PublishDerivedTags(
                    **BASE, derived_id=derived.id, expected_content_rev=derived.content_rev
                ),
            )
        tags = world.rows(
            "SELECT key FROM cur_core_record WHERE type = 'engineering.Tag' ORDER BY key"
        )
        expect(
            [t["key"] for t in tags] == sorted(t[0] for t in TAGS),
            "a publish through the tags target creates the 3 tags",
        )
        links = world.scalar("SELECT COUNT(*) FROM cur_links WHERE relation = 'derived_from'")
        expect(links == 3, "one derived_from link per tag published")
        published = world.rows(
            "SELECT payload FROM events WHERE event_type = 'DerivedDocument.Published'"
        )
        expect(
            len(published) == 1
            and '"target_kind":"tags"' in str(published[0]["payload"]).replace(" ", ""),
            "the Published event keeps its shape and names target_kind tags",
        )
        with open_uow(db) as uow:
            handle_compensate_publication(
                uow, CompensatePublication(**BASE, derived_id=derived.id, reason="acceptance")
            )
        gone = world.scalar(
            "SELECT COUNT(*) FROM cur_core_record WHERE type = 'engineering.Tag' AND NOT "
            "COALESCE(voided, FALSE) AND status <> 'Deleted'"
        )
        expect(gone == 0, "compensation ends exactly the three tags")

        world.register_schema(
            code="doc-register",
            json_schema=DOC_SCHEMA,
            mapping=DOC_MAPPING,
            target_kind="documents",
            key_column="number",
            title="Document register",
        )
        documents = world.open_derived("ISD-001", "A", "doc-register")
        data = b"number,title,discipline\nGA-100,General arrangement,PIP\nGA-101,Sections,PIP\n"
        world.upload_content(documents.id, data, name="register.csv")
        world.start_extraction(derived_id=documents.id)
        world.run_jobs()
        documents = world.derived_row(documents.id)
        with open_uow(db) as uow:
            handle_publish_derived_documents(
                uow,
                PublishDerivedDocuments(
                    **BASE, derived_id=documents.id, expected_content_rev=documents.content_rev
                ),
            )
        docs = world.rows("SELECT key FROM cur_core_record WHERE key LIKE 'GA-%' ORDER BY key")
        expect(
            [d["key"] for d in docs] == ["GA-100", "GA-101"],
            "a publish through the documents target registers the 2 documents",
        )
        with open_uow(db) as uow:
            handle_compensate_publication(
                uow, CompensatePublication(**BASE, derived_id=documents.id, reason="acceptance")
            )
        states = world.rows("SELECT voided FROM cur_core_record WHERE key LIKE 'GA-%'")
        expect(
            len(states) == 2 and all(bool(s["voided"]) for s in states),
            "compensation voids exactly the two documents",
        )
        # an unknown target in force: the command is refused before anything is read
        again = world.open_derived("ISD-001", "A", "instrument-index")
        with use_publish_targets({}):
            expect_raises(
                PublishRefusedError,
                lambda: _publish_tags(db, again),
                "with no tags target registered the publish command is refused",
                "'tags'",
                "none installed",
            )


def _publish_tags(db: Any, derived: Any) -> None:
    with open_uow(db) as uow:
        handle_publish_derived_tags(
            uow, PublishDerivedTags(**BASE, derived_id=derived.id, expected_content_rev=1)
        )


def main() -> int:
    load_registry()
    publish_registry()
    with tempfile.TemporaryDirectory() as raw:
        work = Path(raw)
        loads_through_the_cli(work)
        mapping_form(work)
        publishes(work)
    if failures:
        print("FAILED:", *failures, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Acceptance for P2-I3-S6: ``attach_record_file`` on the embedded, API and fake clients.

Copies ``.accept/p2-i3.db`` (written by ``dev/accept/P2-I3/S3.py --keep``) to a temp directory; when
``TL_PG_URL`` is set it also seeds a fresh Postgres schema with S3's seed. On each backend an
account ``alice`` (role ``user``) is created, a receipt is filed through ``materials_command``, and
the MTR is attached with one client call. The embedded client is given an object store (as the
TUI is at start-up); the API client talks to the app of ``packages/tl-api/tests/harness.py`` in
process. Prints ``PASS <check>`` per check and exits 0; on the first failure prints
``FAIL <check>: <detail>`` and exits 1.

    uv run python dev/accept/P2-I3/S6.py
"""

from __future__ import annotations

import dataclasses
import importlib.util
import inspect
import os
import shutil
import sys
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / ".accept" / "p2-i3.db"
sys.path[:0] = [str(ROOT / "packages/tl-api/tests"), str(ROOT / "packages/tl-tui/tests")]
os.environ.setdefault("TL_ENV", "dev")  # the harness's dev token file is honoured in dev (as S4.py)

from fakes import FakeClient  # noqa: E402
from harness import ALICE, Harness  # noqa: E402
from sqlalchemy import text  # noqa: E402
from tl_adapters.db import DbTarget, as_target, create_schema, open_uow  # noqa: E402
from tl_api.client import ApiClient  # noqa: E402
from tl_core.auth import accounts  # noqa: E402
from tl_core.auth.errors import ForbiddenError  # noqa: E402
from tl_core.files.service import FileResult  # noqa: E402
from tl_core.modules import ConfidentialSource, load_modules, use_modules  # noqa: E402
from tl_core.services.errors import RecordNotFoundError  # noqa: E402
from tl_mod_materials.handlers.receipts import (  # noqa: E402
    AcceptReceipt,
    CreateReceipt,
    InspectReceipt,
)
from tl_tui.client import ClientInterface  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402
from tl_tui.remote import RemoteClient  # noqa: E402

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
FLANGE = "FLG-WN-6-150-A105"
NO_WORD = "svc:no-words"  # an actor that holds no module word
SHARED = ("record_id", "slot", "revision", "sha256", "size", "status", "deduplicated")


class Failure(Exception):
    """One failed check; the message is printed after ``FAIL <check>:``."""


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


@dataclass
class World:
    label: str
    target: DbTarget
    harness: Harness
    embedded: EmbeddedClient
    api: ApiClient
    tmp: Path
    state: dict[str, Any] = field(default_factory=dict[str, Any])

    def events(self) -> int:
        with open_uow(self.target, readonly=True) as uow:
            return int(uow.conn().execute(text("SELECT COUNT(*) FROM events")).scalar_one())

    def one(self, sql: str, **params: Any) -> Any:
        with open_uow(self.target, readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()

    def pdf(self, name: str, body: str) -> Path:
        path = self.tmp / name
        path.write_bytes(f"%PDF-1.4\n{body} {self.label} {uuid.uuid4().hex}\n%%EOF\n".encode())
        return path

    def new_receipt(self, day: str) -> tuple[str, str]:
        made = self.embedded.materials_command(
            "CreateReceipt",
            CreateReceipt(
                actor=ALICE,
                source="tui",
                scope=SCOPE,
                received_on=day,
                location_code="L2",
                po_line=None,
                lines=[
                    {"item_code": FLANGE, "qty": "4.000", "heat_no": "H-S6-1"},  # type: ignore[list-item]
                    {"item_code": FLANGE, "qty": "1.500", "heat_no": "H-S6-2"},  # type: ignore[list-item]
                ],
            ),
        )
        return made.stream_id, str(made.key)


def raised(call: Callable[[], object], error: type[BaseException]) -> BaseException:
    try:
        call()
    except error as caught:
        return caught
    raise Failure(f"expected {error.__name__}, nothing was raised")


def check_create_receipt(w: World) -> None:
    receipt_id, number = w.new_receipt("2026-11-05")
    detail = w.embedded.get_materials_receipt(PROJECT, number)
    expect(detail.id == receipt_id, f"CommandResult.stream_id {receipt_id} != view id {detail.id}")
    expect(detail.mtr == "missing" and detail.mtr_required, f"mtr is {detail.mtr}")
    w.state.update(receipt_id=receipt_id, number=number)


def check_attach(w: World) -> None:
    path = w.pdf("mtr.pdf", "mill test report")
    w.state["mtr"] = path
    before = w.events()
    result = w.embedded.attach_record_file(w.state["receipt_id"], path, slot="mtr")
    expect(isinstance(result, FileResult), f"returned {type(result).__name__}")
    expect(result.status == "available", f"status {result.status}")  # inline scan passes it
    expect(result.slot == "mtr" and not result.already_attached, "slot or already_attached wrong")
    expect(w.events() > before, "no event was written")
    w.state["first"] = result


def check_detail_and_listing(w: World) -> None:
    detail = w.embedded.get_materials_receipt(PROJECT, w.state["number"])
    expect(detail.mtr == "present", f"mtr is {detail.mtr}")
    listed = w.embedded.list_record_files(w.state["receipt_id"])
    expect([(i.slot, i.status) for i in listed] == [("mtr", "available")], f"listed {listed}")
    expect(listed[0].filename == "mtr.pdf", f"filename {listed[0].filename}")


def check_inspect_accept(w: World) -> None:
    receipt_id, number = w.state["receipt_id"], w.state["number"]
    w.embedded.materials_command(
        "InspectReceipt",
        InspectReceipt(actor=ALICE, source="tui", scope=SCOPE, stream_id=receipt_id),
    )
    version = w.one("SELECT version FROM cur_core_record WHERE id = :i", i=receipt_id)
    w.embedded.materials_command(
        "AcceptReceipt",
        AcceptReceipt(
            actor=ALICE, source="tui", scope=SCOPE, stream_id=receipt_id, expected_version=version
        ),
    )
    lots = [r.lot for r in w.embedded.list_materials_stock(PROJECT, limit=1000)]
    mine = sorted(lot for lot in lots if lot.startswith(number + "@"))
    expect(mine == [f"{number}@1", f"{number}@2"], f"lots {mine}")


def check_second_call(w: World) -> None:
    before = w.events()
    again = w.embedded.attach_record_file(w.state["receipt_id"], w.state["mtr"], slot="mtr")
    expect(again.already_attached or again.deduplicated, f"second call: {again}")
    expect(again.file_id == w.state["first"].file_id, "a second file was made")
    expect(w.events() == before, "the second call wrote an event")


def check_missing_and_hidden(w: World) -> None:
    receipt_id, _ = w.new_receipt("2026-11-06")
    other_id, _ = w.new_receipt("2026-11-07")
    w.state.update(visible_id=receipt_id, hidden_id=other_id)
    with open_uow(w.target) as uow:
        conn = uow.conn()
        conn.execute(text("CREATE TABLE x_class (id TEXT PRIMARY KEY, cls TEXT)"))
        for (rid,) in conn.execute(
            text("SELECT id FROM cur_core_record WHERE type = 'materials.Receipt'")
        ).all():
            cls = "restricted" if rid == other_id else "internal"
            conn.execute(text("INSERT INTO x_class VALUES (:i, :c)"), {"i": str(rid), "c": cls})
    receipt = next(m for m in load_modules() if "materials.Receipt" in m.record_types)
    source = ConfidentialSource(
        record_types=frozenset({"materials.Receipt"}),
        table="x_class",
        id_column="id",
        class_column="cls",
    )
    changed = [
        dataclasses.replace(m, confidential=(source,)) if m.name == receipt.name else m
        for m in load_modules()
    ]
    path = w.pdf("hidden.pdf", "hidden")
    made_up = "01ZZZZZZZZZZZZZZZZZZZZZZZZ"
    with use_modules(changed):
        for label, client in (("embedded", w.embedded), ("api", w.api)):
            before = w.events()
            hidden = raised(
                lambda c=client: c.attach_record_file(other_id, path, slot="mtr"),  # type: ignore[misc]
                RecordNotFoundError,
            )
            missing = raised(
                lambda c=client: c.attach_record_file(made_up, path, slot="mtr"),  # type: ignore[misc]
                RecordNotFoundError,
            )
            same = str(hidden).replace(other_id, "<id>") == str(missing).replace(made_up, "<id>")
            expect(same, f"{label}: hidden says {hidden!s}, missing says {missing!s}")
            expect(w.events() == before, f"{label}: a refused call wrote an event")


def check_no_word(w: World) -> None:
    nobody = EmbeddedClient(w.harness.backend, actor=NO_WORD, object_store=w.harness.store)
    before = w.events()
    raised(
        lambda: nobody.attach_record_file(w.state["visible_id"], w.pdf("n.pdf", "n"), slot="mtr"),
        ForbiddenError,
    )
    expect(w.events() == before, "a refused call wrote an event")


def check_missing_path(w: World) -> None:
    before = w.events()
    gone = w.tmp / "no-such-file.pdf"
    for label, client in (("embedded", w.embedded), ("api", w.api)):
        raised(
            lambda c=client: c.attach_record_file(w.state["visible_id"], gone, slot="mtr"),
            FileNotFoundError,
        )  # type: ignore[misc]
        expect(w.events() == before, f"{label}: a missing path wrote an event")


def check_api_and_fake_agree(w: World) -> None:
    record_id = w.state["visible_id"]
    path = w.pdf("api.pdf", "through the api")
    fake = FakeClient()
    fake.set_actions(record_id)  # the fake knows the record
    api_result = w.api.attach_record_file(record_id, path, slot="mtr")
    fake_result = fake.attach_record_file(record_id, path, slot="mtr")
    api_shape = api_result.model_dump(include=set(SHARED))
    fake_shape = fake_result.model_dump(include=set(SHARED))
    expect(api_shape == fake_shape, f"api {api_shape} != fake {fake_shape}")
    expect(api_result.status == "available", f"api status {api_result.status}")
    listed = [(i.slot, i.filename) for i in fake.list_record_files(record_id)]
    expect(listed == [("mtr", "api.pdf")], f"fake lists {listed}")
    expect(fake.attached_files == [(record_id, "api.pdf", "mtr")], "fake did not record the call")
    again = fake.attach_record_file(record_id, path, slot="mtr")
    expect(again.already_attached, "fake: the same bytes twice were not already_attached")
    raised(lambda: fake.attach_record_file("NO-SUCH", path), RecordNotFoundError)
    raised(lambda: fake.attach_record_file(record_id, w.tmp / "nope.pdf"), FileNotFoundError)


def check_embedded_lists_api_upload(w: World) -> None:
    listed = w.embedded.list_record_files(w.state["visible_id"])
    expect([(i.slot, i.filename) for i in listed] == [("mtr", "api.pdf")], f"listed {listed}")


def check_methods_on_all_classes(_: World) -> None:
    for cls in (ClientInterface, EmbeddedClient, ApiClient, FakeClient):
        expect(callable(getattr(cls, "attach_record_file", None)), f"{cls.__name__} lacks it")
    want = _params(ClientInterface)
    for cls in (EmbeddedClient, ApiClient, FakeClient):
        expect(_params(cls) == want, f"{cls.__name__}: {_params(cls)} != {want}")
    remote = RemoteClient(ApiClient("http://testserver", "t"))
    expect(callable(remote.attach_record_file), "RemoteClient does not serve it")  # type: ignore[attr-defined]


def _params(cls: type) -> list[tuple[str, Any, Any]]:
    sig = inspect.signature(cls.attach_record_file)  # type: ignore[attr-defined]
    return [(p.name, p.kind, p.default) for p in sig.parameters.values() if p.name != "self"]


CHECKS: list[tuple[str, Callable[[World], None]]] = [
    ("a receipt is filed; its id is stream_id; mtr is missing", check_create_receipt),
    ("attach_record_file(mtr) gives an available FileResult", check_attach),
    ("receipt_detail.mtr is present; list_record_files lists mtr", check_detail_and_listing),
    ("the same bytes again: already_attached, no new event", check_second_call),
    ("the receipt Inspects and Accepts; both lots exist", check_inspect_accept),
    ("hidden and made-up ids: same text, no event", check_missing_and_hidden),
    ("an actor without the word is refused, no event", check_no_word),
    ("a missing path raises FileNotFoundError, no event", check_missing_path),
    ("ApiClient and the fake return equal shapes", check_api_and_fake_agree),
    ("the embedded client lists the API client's file", check_embedded_lists_api_upload),
    ("attach_record_file: one signature on all client classes", check_methods_on_all_classes),
]


def run_backend(label: str, target: DbTarget, root: Path) -> int:
    api_root = root / f"api-{label}"
    api_root.mkdir()
    harness = Harness.build(api_root, target=target)
    try:
        with open_uow(target) as uow:
            accounts.create_account(
                uow,
                username="alice",
                display_name="Alice",
                kind="person",
                roles=["user"],
                password=None,
                by="user:seed",
            )
        embedded = EmbeddedClient(harness.backend, actor=ALICE, object_store=harness.store)
        tmp = root / f"files-{label}"
        tmp.mkdir()
        world = World(label, target, harness, embedded, harness.api(ALICE), tmp)
        for name, check in CHECKS:
            try:
                check(world)
            except Failure as exc:
                print(f"FAIL {label}: {name}: {exc}")
                return 1
            print(f"PASS {label}: {name}")
        return 0
    finally:
        harness.close()


def seed_postgres(url: str, root: Path) -> tuple[DbTarget, Callable[[], None]]:
    """A fresh schema with S3's seed (the same ledger as the SQLite file)."""
    from tl_adapters.postgres import admin

    spec = importlib.util.spec_from_file_location("accept_s3", Path(__file__).with_name("S3.py"))
    assert spec is not None and spec.loader is not None
    s3 = importlib.util.module_from_spec(spec)
    sys.modules["accept_s3"] = s3
    spec.loader.exec_module(s3)
    schema = "tl_acc_" + uuid.uuid4().hex[:12]
    admin.create_schema_namespace(url, schema)
    target = as_target(admin.schema_url(url, schema))
    create_schema(target)
    world = s3.World(target, root / "objects")
    world.project = SCOPE
    world.number = PROJECT
    s3.seed(world)
    return target, lambda: admin.drop_schema_namespace(url, schema)


def main() -> int:
    if not LEDGER.exists():
        print(f"FAIL ledger: {LEDGER} is missing (run dev/accept/P2-I3/S3.py --keep first)")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / "tl.db"
        for src in LEDGER.parent.glob(LEDGER.name + "*"):  # the ledger and any WAL sidecars
            shutil.copy(src, root / ("tl.db" + src.name[len(LEDGER.name) :]))
        status = run_backend("sqlite", as_target(db), root)
        url = os.environ.get("TL_PG_URL")
        if status == 0 and url:
            target, drop = seed_postgres(url, root)
            try:
                status = run_backend("postgres", target, root)
            finally:
                drop()
    return status


if __name__ == "__main__":
    sys.exit(main())

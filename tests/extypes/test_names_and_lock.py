"""Names of extension types and the ``type.lock`` rules (brief 31.1; FANOUT D7, D9)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest
from tl_core.extypes import lock
from tl_core.extypes.names import (
    LayoutError,
    coordinates,
    package_coordinates,
    parse_type_ref,
    pset_name,
    snake_case,
    split_type_name,
    stream_id,
)

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures" / "types"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("LiftPlan", "lift_plan"),
        ("Lift", "lift"),
        ("HTTPServer", "http_server"),
        ("Plan2Go", "plan2_go"),
        ("SafetyObservation", "safety_observation"),
    ],
)
def test_snake_case(name: str, expected: str) -> None:
    assert snake_case(name) == expected


def test_the_pset_is_named_for_the_type() -> None:
    assert pset_name("co.acme", "LiftPlan") == "co_acme_lift_plan"
    assert "__" not in pset_name("a.b.c", "XY")


def test_type_refs_round_trip() -> None:
    coords = parse_type_ref("co.acme.LiftPlan@1.2.0")
    assert (coords.namespace, coords.name, coords.version) == ("co.acme", "LiftPlan", "1.2.0")
    assert coords.type_name == "co.acme.LiftPlan"
    assert coords.type_ref == "co.acme.LiftPlan@1.2.0"
    assert stream_id(coords.type_ref) == "type:co.acme.LiftPlan@1.2.0"
    assert split_type_name("co.acme.LiftPlan") == ("co.acme", "LiftPlan")


@pytest.mark.parametrize(
    "bad",
    ["LiftPlan", "co.acme.lift@1.0.0", "co.acme.LiftPlan@1.0", "co.acme.LiftPlan@01.0.0", ""],
)
def test_malformed_type_refs_are_refused(bad: str) -> None:
    with pytest.raises(LayoutError):
        parse_type_ref(bad)


@pytest.mark.parametrize(
    ("namespace", "name", "version"),
    [
        ("Co.Acme", "LiftPlan", "1.0.0"),
        ("co.acme", "liftPlan", "1.0.0"),
        ("co.acme", "LiftPlan", "v1"),
        ("co_acme", "LiftPlan", "1.0.0"),
        ("core", "Thing", "1.0.0"),
        ("tl.x", "Thing", "1.0.0"),
    ],
)
def test_bad_coordinates_are_refused(namespace: str, name: str, version: str) -> None:
    with pytest.raises(LayoutError):
        coordinates(namespace, name, version)


def test_a_package_path_has_exactly_three_levels(tmp_path: Path) -> None:
    ok = tmp_path / "co.acme" / "LiftPlan" / "1.0.0"
    ok.mkdir(parents=True)
    assert package_coordinates(tmp_path, ok).type_ref == "co.acme.LiftPlan@1.0.0"
    deep = tmp_path / "co.acme" / "LiftPlan" / "1.0.0" / "extra"
    deep.mkdir()
    with pytest.raises(LayoutError, match="levels"):
        package_coordinates(tmp_path, deep)
    shallow = tmp_path / "co.acme"
    with pytest.raises(LayoutError):
        package_coordinates(tmp_path, shallow)
    with pytest.raises(LayoutError, match="not below"):
        package_coordinates(tmp_path / "elsewhere", ok)


# --- type.lock ------------------------------------------------------------------------------------


def copy_package(tmp_path: Path, name: str = "LiftPlan") -> Path:
    target = tmp_path / "pkg"
    shutil.copytree(FIXTURES / "co.acme" / name / "1.0.0", target)
    return target


def test_the_committed_locks_are_current() -> None:
    for name in ("LiftPlan", "SafetyObservation"):
        assert lock.lock_issues(FIXTURES / "co.acme" / name / "1.0.0") == []


def test_content_hash_is_the_sha256_of_the_canonical_lock_bytes(tmp_path: Path) -> None:
    package = copy_package(tmp_path)
    files, issues = lock.compute_lock(package)
    assert issues == []
    expected_bytes = json.dumps({"files": files}, sort_keys=True, separators=(",", ":")).encode()
    assert lock.canonical_lock_bytes(files) == expected_bytes
    assert lock.content_hash(files) == hashlib.sha256(expected_bytes).hexdigest()
    assert (package / "type.lock").read_bytes() == expected_bytes
    assert "type.lock" not in files


def test_the_lock_lists_every_file_below_the_package(tmp_path: Path) -> None:
    package = copy_package(tmp_path)
    files, _ = lock.compute_lock(package)
    assert set(files) >= {"type.yaml", "form.yaml", "examples/crane-12-routine.json"}
    (package / "templates").mkdir()
    (package / "templates" / "report.txt").write_text("x")
    (package / ".hidden").write_text("x")
    again, _ = lock.compute_lock(package)
    assert "templates/report.txt" in again and ".hidden" not in again


def test_a_lock_written_with_other_whitespace_still_hashes_the_same(tmp_path: Path) -> None:
    package = copy_package(tmp_path)
    files, _ = lock.compute_lock(package)
    (package / "type.lock").write_text(json.dumps({"files": files}, indent=2) + "\n")
    declared = lock.read_lock(package)
    assert declared is not None and declared == files
    assert lock.lock_issues(package) == []
    assert lock.content_hash(declared) == lock.content_hash(files)


def test_a_changed_file_is_a_lock_issue_naming_the_file(tmp_path: Path) -> None:
    package = copy_package(tmp_path)
    (package / "form.yaml").write_text((package / "form.yaml").read_text() + "# edit\n")
    issues = lock.lock_issues(package)
    assert [(i.kind, i.path, i.detail) for i in issues] == [
        ("lock", "form.yaml", "hash differs from type.lock")
    ]


def test_an_added_and_a_removed_file_are_lock_issues(tmp_path: Path) -> None:
    package = copy_package(tmp_path)
    (package / "new.txt").write_text("x")
    (package / "form.yaml").unlink()
    found = {(i.path, i.detail) for i in lock.lock_issues(package)}
    assert found == {
        ("new.txt", "not listed in type.lock"),
        ("form.yaml", "listed in type.lock but the file is missing"),
    }


def test_a_missing_or_unreadable_lock_is_a_lock_issue(tmp_path: Path) -> None:
    package = copy_package(tmp_path)
    (package / "type.lock").unlink()
    assert [i.detail for i in lock.lock_issues(package)] == ["type.lock is missing"]
    (package / "type.lock").write_text("not json")
    assert lock.lock_issues(package)[0].kind == "lock"
    (package / "type.lock").write_text('{"files": {"a": 1}}')
    assert "must look like" in lock.lock_issues(package)[0].detail


def test_a_symbolic_link_is_refused_and_never_followed(tmp_path: Path) -> None:
    package = copy_package(tmp_path)
    outside = tmp_path / "secret.txt"
    outside.write_text("do not read")
    os.symlink(outside, package / "link.txt")
    os.symlink(tmp_path, package / "linked-dir")
    files, issues = lock.compute_lock(package)
    assert "link.txt" not in files and not any(f.startswith("linked-dir") for f in files)
    assert {(i.kind, i.path) for i in issues} == {("layout", "link.txt"), ("layout", "linked-dir")}


def test_an_oversized_file_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = copy_package(tmp_path)
    monkeypatch.setattr(lock, "MAX_FILE_BYTES", 100)
    _, issues = lock.compute_lock(package)
    assert any(i.kind == "layout" and "larger than" in i.detail for i in issues)


def test_write_lock_returns_the_content_hash_and_is_idempotent(tmp_path: Path) -> None:
    package = copy_package(tmp_path)
    first = lock.write_lock(package)
    second = lock.write_lock(package)
    assert first == second == lock.content_hash(lock.compute_lock(package)[0])

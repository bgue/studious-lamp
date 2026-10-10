"""The dev-data guard (FANOUT D12): which databases, tests, URLs and documents it allows."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_mcp.dev.errors import DevGuardError
from tl_mcp.dev.guard import (
    check_environment,
    check_loopback_url,
    find_repo_root,
    list_documents,
    resolve_target,
    safe_child,
    select_pytest_args,
)

REPO = find_repo_root()


# --- the database ------------------------------------------------------------------------------


def test_a_sqlite_file_in_a_temp_directory_is_dev_data(tmp_path: Path) -> None:
    target = resolve_target(tmp_path / "x.db", repo_root=REPO)
    assert target.kind == "sqlite" and target.path == (tmp_path / "x.db").resolve()


def test_a_sqlite_file_under_dev_is_dev_data() -> None:
    assert resolve_target("dev/data/tl.db", repo_root=REPO).path == REPO / "dev/data/tl.db"
    assert resolve_target(REPO / "dev/demos/x.db", repo_root=REPO).kind == "sqlite"


# The repository can itself be checked out under a temporary directory (a CI runner, /tmp), which
# the guard allows, so the paths that are relative to the repository are tried against a repository
# root that is certainly not under one.
NOT_UNDER_TMP = Path("/srv/throughline-not-a-real-checkout")


@pytest.mark.parametrize(
    "raw",
    [
        "tl.db",  # the repository root itself is not dev/
        "packages/tl-core/x.db",
        "dev/../tl.db",
        "dev/data/../../tl.db",
    ],
)
def test_a_relative_sqlite_path_outside_dev_is_refused(raw: str) -> None:
    with pytest.raises(DevGuardError):
        resolve_target(raw, repo_root=NOT_UNDER_TMP)
    assert resolve_target("dev/data/tl.db", repo_root=NOT_UNDER_TMP).path == (
        NOT_UNDER_TMP / "dev/data/tl.db"
    )


@pytest.mark.parametrize(
    "raw",
    [
        "/etc/passwd",
        "/home/user/other.db",
        "/tmp-evil/x.db",  # a sibling whose name starts like the temp directory
        "file:/tmp/x.db",
        "sqlite:////tmp/x.db",
        "/tmp/x.db\x00.txt",
        "",
    ],
)
def test_a_sqlite_path_outside_dev_data_is_refused(raw: str) -> None:
    with pytest.raises(DevGuardError):
        resolve_target(raw, repo_root=NOT_UNDER_TMP)


def test_a_symlink_that_leaves_the_allowed_roots_is_refused(tmp_path: Path) -> None:
    link = tmp_path / "link.db"
    link.symlink_to("/etc/hostname")
    with pytest.raises(DevGuardError, match="dev/ directory or a temporary"):
        resolve_target(link, repo_root=REPO, extra_roots=())
    # the same link is fine for a root it really points into
    assert resolve_target(link, repo_root=REPO, extra_roots=[Path("/etc")]).path == Path(
        "/etc/hostname"
    )


def test_a_directory_is_not_a_database(tmp_path: Path) -> None:
    with pytest.raises(DevGuardError, match="directory"):
        resolve_target(tmp_path, repo_root=REPO)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://postgres:pw@localhost:5432/tl_test",
        "postgresql://postgres:pw@127.0.0.1/tl_dev",
        "postgres://u@/tl_dev_scratch",
        "postgresql://postgres:pw@localhost/tl_test?options=-csearch_path%3Dtl_t_ab12",
    ],
)
def test_a_local_tl_test_or_tl_dev_postgres_is_dev_data(url: str) -> None:
    target = resolve_target(url, repo_root=REPO)
    assert target.kind == "postgres" and target.url == url


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://postgres:pw@localhost:5432/postgres",
        "postgresql://postgres:pw@localhost:5432/tl",
        "postgresql://postgres:pw@localhost:5432/prod_tl_test",
        "postgresql://postgres:pw@localhost:5432/",
        "postgresql://postgres:pw@db.example.com:5432/tl_test",
        "postgresql://postgres:pw@10.0.0.5/tl_dev",
        "postgresql://postgres:pw@localhost/tl_test?host=db.example.com",
        "postgresql://postgres:pw@localhost/tl_test?options=-csearch_path%3Dx;drop",
        "postgresql://postgres:pw@localhost/tl_test?sslmode=disable",
        "postgresql+pg8000://postgres:pw@localhost/tl_test",
        "mysql://u@localhost/tl_test",
    ],
)
def test_any_other_postgres_is_refused(url: str) -> None:
    with pytest.raises(DevGuardError):
        resolve_target(url, repo_root=REPO)


def test_the_displayed_target_never_holds_a_password() -> None:
    target = resolve_target("postgresql://postgres:s3cret@localhost/tl_test", repo_root=REPO)
    assert "s3cret" not in target.display
    assert resolve_target("dev/data/tl.db", repo_root=REPO).display == "tl.db"


@pytest.mark.parametrize("value", ["prod", "production", "staging", "PROD"])
def test_a_real_environment_is_refused(value: str) -> None:
    with pytest.raises(DevGuardError, match="TL_ENV"):
        check_environment({"TL_ENV": value})


@pytest.mark.parametrize("env", [{}, {"TL_ENV": "dev"}, {"TL_ENV": "test"}, {"TL_ENV": "CI"}])
def test_dev_test_and_ci_environments_are_allowed(env: dict[str, str]) -> None:
    check_environment(env)


# --- tests -------------------------------------------------------------------------------------


def test_a_marker_a_keyword_and_test_paths_become_the_pytest_arguments() -> None:
    args = select_pytest_args(
        repo_root=REPO,
        paths=["packages/tl-mcp/tests/test_dev_guard.py", "tests/property"],
        marker="parity",
        keyword="guard and not slow",
        adapters="sqlite,postgres",
    )
    assert args == [
        "-q",
        "-p",
        "no:cacheprovider",
        "-m",
        "parity",
        "-k",
        "guard and not slow",
        "--adapters",
        "sqlite,postgres",
        "packages/tl-mcp/tests/test_dev_guard.py",
        "tests/property",
    ]


def test_a_test_name_can_follow_the_file() -> None:
    args = select_pytest_args(
        repo_root=REPO,
        paths=["packages/tl-mcp/tests/test_dev_guard.py::test_a_directory_is_not_a_database"],
    )
    assert args[-1].endswith("::test_a_directory_is_not_a_database")


@pytest.mark.parametrize(
    "paths",
    [
        ["--co"],
        ["-x"],
        ["/etc/passwd"],
        ["../etc"],
        ["tests/../../etc"],
        ["packages/tl-core/src/tl_core/ledger"],  # not a tests directory
        ["tests/does_not_exist.py"],
        ["tests/property; rm -rf /"],
        ["tests/property --pdb"],
        ["conftest.py"],
        ["packages/tl-mcp/tests/test_dev_guard.py::t[1]"],
    ],
)
def test_a_test_path_outside_the_allow_list_is_refused(paths: list[str]) -> None:
    with pytest.raises(DevGuardError):
        select_pytest_args(repo_root=REPO, paths=paths)


@pytest.mark.parametrize("marker", ["slow", "parity or x", "-x", "", "bench"])
def test_a_marker_outside_the_allow_list_is_refused(marker: str) -> None:
    with pytest.raises(DevGuardError, match="marker"):
        select_pytest_args(repo_root=REPO, marker=marker)


@pytest.mark.parametrize("keyword", ["-x", "a;b", "a $(id)", "a\nb", "a\n", "x" * 201, "", "a.b"])
def test_a_keyword_with_other_characters_is_refused(keyword: str) -> None:
    with pytest.raises(DevGuardError, match="keyword"):
        select_pytest_args(repo_root=REPO, keyword=keyword)


def test_adapters_outside_the_list_are_refused() -> None:
    with pytest.raises(DevGuardError, match="adapters"):
        select_pytest_args(repo_root=REPO, adapters="mysql")


# --- webhooks ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "ip", "port", "path"),
    [
        ("http://127.0.0.1:9000/hook", "127.0.0.1", 9000, "/hook"),
        ("http://localhost:9000", "127.0.0.1", 9000, "/"),
        ("http://LOCALHOST/a?b=1", "127.0.0.1", 80, "/a?b=1"),
        ("https://127.1.2.3/x", "127.1.2.3", 443, "/x"),
        ("http://[::1]:8080/h", "::1", 8080, "/h"),
        ("http://[::ffff:127.0.0.1]:81/h", "127.0.0.1", 81, "/h"),
    ],
)
def test_a_loopback_target_is_accepted_and_resolved_without_dns(
    url: str, ip: str, port: int, path: str
) -> None:
    target = check_loopback_url(url)
    assert (target.ip, target.port, target.path_and_query) == (ip, port, path)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/hook",
        "http://8.8.8.8/hook",
        "http://10.0.0.1/hook",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data",
        "http://0.0.0.0:80/",
        "http://2130706433/",  # decimal spelling of 127.0.0.1
        "http://0x7f.0.0.1/",
        "http://0177.0.0.1/",
        "http://127.0.0.1.nip.io/",
        "http://localhost.evil.com/",
        "http://127.0.0.1@evil.com/",
        "http://user:pw@127.0.0.1/",
        "http://127.0.0.1/#frag",
        "ftp://127.0.0.1/",
        "file:///etc/passwd",
        "gopher://127.0.0.1/",
        "http://[::2]/",
        "http://127.0.0.1:99999/",
        "http://127.0.0.1/ x",
        "http://127.0.0.1/\x00",
        "//127.0.0.1/",
        "",
    ],
)
def test_any_other_target_is_refused(url: str) -> None:
    with pytest.raises(DevGuardError):
        check_loopback_url(url)


# --- documents ---------------------------------------------------------------------------------


def test_a_document_is_found_by_its_plain_name(tmp_path: Path) -> None:
    (tmp_path / "0001-a.md").write_text("x")
    (tmp_path / "notes.txt").write_text("x")
    assert safe_child(tmp_path, "0001-a.md", [".md"]) == (tmp_path / "0001-a.md").resolve()
    assert list_documents(tmp_path, [".md"]) == ["0001-a.md"]
    assert list_documents(tmp_path / "missing", [".md"]) == []


@pytest.mark.parametrize(
    "name",
    [
        "../x.md",
        "a/b.md",
        "..",
        ".hidden.md",
        "a..b.md",
        "x.txt",
        "",
        "a\x00.md",
        "x.md\n",
        "x" * 200,
    ],
)
def test_a_name_that_is_not_a_plain_document_name_is_refused(tmp_path: Path, name: str) -> None:
    (tmp_path / "x.txt").write_text("x")
    with pytest.raises(DevGuardError):
        safe_child(tmp_path, name, [".md"])


def test_a_symlink_that_leaves_the_directory_is_not_a_document(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    outside = tmp_path / "secret.md"
    outside.write_text("secret")
    (docs / "link.md").symlink_to(outside)
    with pytest.raises(DevGuardError):
        safe_child(docs, "link.md", [".md"])
    assert list_documents(docs, [".md"]) == []

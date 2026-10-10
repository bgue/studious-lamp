"""Dev resources: ADRs, runbooks and stored test reports (brief 25.2, 25.3; FANOUT D12)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from dev_harness import DevHarness
from mcp.server.mcpserver.exceptions import ResourceError
from tl_mcp.dev.guard import find_repo_root

ADR_INDEX = "tl://dev/adrs"
RUNBOOK_INDEX = "tl://dev/runbooks"
REPORT_INDEX = "tl://dev/test-reports"
MAX_BYTES = 1024 * 1024


def _tree(tmp_path: Path) -> Path:
    """A small repository copy: the three document directories, AGENTS.md and justfile."""
    repo = tmp_path / "repo"
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "docs" / "runbooks").mkdir(parents=True)
    (repo / "dev" / "data" / "test-reports").mkdir(parents=True)
    (repo / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (repo / "justfile").write_text("default:\n    @just --list\n", encoding="utf-8")
    return repo


@pytest.fixture
def tree(tmp_path: Path) -> tuple[DevHarness, Path]:
    repo = _tree(tmp_path)
    return DevHarness.build(tmp_path, repo_root=repo), repo


def _index(env: DevHarness, uri: str) -> list[dict[str, object]]:
    loaded = json.loads(env.read(uri))
    assert isinstance(loaded, list)
    return loaded


# --- the six resources ---------------------------------------------------------------------------


def test_six_resources_are_listed(dev_env: DevHarness) -> None:
    uris = dev_env.resource_uris()
    for uri in (
        "tl://dev/adrs",
        "tl://dev/runbooks",
        "tl://dev/test-reports",
        "tl://dev/adr/{name}",
        "tl://dev/runbook/{name}",
        "tl://dev/test-report/{name}",
    ):
        assert uri in uris


# --- the real repository -------------------------------------------------------------------------


def test_real_adr_index_has_relay_orchestration(dev_env: DevHarness) -> None:
    entries = {entry["name"]: entry for entry in _index(dev_env, ADR_INDEX)}
    assert "0004-relay-orchestration" in entries
    entry = entries["0004-relay-orchestration"]
    assert entry["status"] == "accepted"
    assert "Relay orchestration" in str(entry["title"])


def test_real_adr_document_is_the_file_text(dev_env: DevHarness) -> None:
    path = find_repo_root() / "docs" / "adr" / "0004-relay-orchestration.md"
    text = dev_env.read("tl://dev/adr/0004-relay-orchestration")
    assert text == path.read_bytes().decode("utf-8")


def test_real_runbook_index_has_tui_dev_and_no_readme(dev_env: DevHarness) -> None:
    names = [str(entry["name"]) for entry in _index(dev_env, RUNBOOK_INDEX)]
    assert "tui-dev" in names
    assert "README" not in names
    assert names == sorted(names)


def test_readme_runbook_is_not_served(dev_env: DevHarness) -> None:
    with pytest.raises(ResourceError, match="no such document"):
        dev_env.read("tl://dev/runbook/README")
    with pytest.raises(ResourceError, match="no such document"):
        dev_env.read("tl://dev/runbook/README.md")


# --- a small tree --------------------------------------------------------------------------------


def test_adr_without_status_has_null_status(tree: tuple[DevHarness, Path]) -> None:
    env, repo = tree
    (repo / "docs" / "adr" / "0001-no-status.md").write_text(
        "# ADR-0001 No status line\n\nBody only.\n", encoding="utf-8"
    )
    (repo / "docs" / "adr" / "0002-accepted.md").write_text(
        "# ADR-0002 Has one\n\nStatus: accepted\n", encoding="utf-8"
    )
    entries = {str(e["name"]): e for e in _index(env, ADR_INDEX)}
    assert entries["0001-no-status"]["status"] is None
    assert entries["0001-no-status"]["title"] == "ADR-0001 No status line"
    assert entries["0002-accepted"]["status"] == "accepted"


def test_title_falls_back_to_name_without_heading(tree: tuple[DevHarness, Path]) -> None:
    env, repo = tree
    (repo / "docs" / "adr" / "0003-untitled.md").write_text(
        "Status: proposed\n\nno heading here\n", encoding="utf-8"
    )
    entries = _index(env, ADR_INDEX)
    assert entries == [{"name": "0003-untitled", "title": "0003-untitled", "status": "proposed"}]


def test_second_level_heading_is_not_a_title(tree: tuple[DevHarness, Path]) -> None:
    env, repo = tree
    (repo / "docs" / "adr" / "0004-sub.md").write_text(
        "## Context\n\nStatus: draft\n", encoding="utf-8"
    )
    entry = _index(env, ADR_INDEX)[0]
    assert entry["title"] == "0004-sub"
    assert entry["status"] == "draft"


def test_index_is_sorted_by_name(tree: tuple[DevHarness, Path]) -> None:
    env, repo = tree
    for name in ("0010-b", "0002-a", "0001-c"):
        (repo / "docs" / "adr" / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")
    names = [str(e["name"]) for e in _index(env, ADR_INDEX)]
    assert names == ["0001-c", "0002-a", "0010-b"]


def test_runbook_index_leaves_out_readme(tree: tuple[DevHarness, Path]) -> None:
    env, repo = tree
    (repo / "docs" / "runbooks" / "README.md").write_text("# Index\n", encoding="utf-8")
    (repo / "docs" / "runbooks" / "tui-dev.md").write_text(
        "# Runbook TUI dev\n\nStatus: ready\n", encoding="utf-8"
    )
    entries = _index(env, RUNBOOK_INDEX)
    assert entries == [{"name": "tui-dev", "title": "Runbook TUI dev", "status": "ready"}]


def test_reports_are_newest_first_with_byte_sizes(tree: tuple[DevHarness, Path]) -> None:
    env, repo = tree
    reports = repo / "dev" / "data" / "test-reports"
    (reports / "20261009T100000Z-aaaaaa.txt").write_bytes(b"12345")
    (reports / "20261010T120000Z-ab12cd.txt").write_bytes(b"123456789012")
    (reports / "20261008T000000Z-ff00ff.txt").write_bytes(b"123")
    (reports / "notes.log").write_bytes(b"not a report")
    assert _index(env, REPORT_INDEX) == [
        {"name": "20261010T120000Z-ab12cd.txt", "bytes": 12},
        {"name": "20261009T100000Z-aaaaaa.txt", "bytes": 5},
        {"name": "20261008T000000Z-ff00ff.txt", "bytes": 3},
    ]


def test_report_index_holds_at_most_100(tree: tuple[DevHarness, Path]) -> None:
    env, repo = tree
    reports = repo / "dev" / "data" / "test-reports"
    for i in range(101):
        (reports / f"20250101T000000Z-{i:06x}.txt").write_bytes(b"x")
    entries = _index(env, REPORT_INDEX)
    names = [str(e["name"]) for e in entries]
    assert len(names) == 100
    assert names[0] == f"20250101T000000Z-{100:06x}.txt"
    assert f"20250101T000000Z-{0:06x}.txt" not in names


def test_missing_reports_directory_gives_empty_index(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "docs" / "runbooks").mkdir(parents=True)
    env = DevHarness.build(tmp_path, repo_root=repo)
    assert _index(env, REPORT_INDEX) == []
    assert _index(env, ADR_INDEX) == []


def test_report_document_is_read(tree: tuple[DevHarness, Path]) -> None:
    env, repo = tree
    name = "20261010T120000Z-ab12cd.txt"
    (repo / "dev" / "data" / "test-reports" / name).write_text("3 passed\n", encoding="utf-8")
    assert env.read(f"tl://dev/test-report/{name}") == "3 passed\n"


def test_adr_document_is_read_from_small_tree(tree: tuple[DevHarness, Path]) -> None:
    env, repo = tree
    body = "# ADR-0005 Small\n\nStatus: accepted\n\nBody.\n"
    (repo / "docs" / "adr" / "0005-small.md").write_text(body, encoding="utf-8")
    assert env.read("tl://dev/adr/0005-small") == body


# --- refusals ------------------------------------------------------------------------------------


ODD_TAILS = [
    "../../etc/passwd",
    "..",
    "a%2Fb",
    ".hidden",
    "x%00y",
    "a" * 200,
    "0004-relay-orchestration.md",
]


def _refusal_text(message: str) -> bool:
    """The SDK rejects a URI that does not match the template ("Unknown resource: <uri>"); a name
    that matches reaches the guard and is "no such document". Neither text holds a path."""
    return message == "no such document" or message.startswith("Unknown resource: tl://dev/")


@pytest.mark.parametrize("tail", ODD_TAILS)
def test_odd_adr_names_are_refused(dev_env: DevHarness, tail: str, tmp_path: Path) -> None:
    with pytest.raises(ResourceError) as info:
        dev_env.read(f"tl://dev/adr/{tail}")
    assert _refusal_text(str(info.value))
    assert str(tmp_path) not in str(info.value)


@pytest.mark.parametrize("tail", ODD_TAILS)
def test_odd_report_names_are_refused(dev_env: DevHarness, tail: str, tmp_path: Path) -> None:
    with pytest.raises(ResourceError) as info:
        dev_env.read(f"tl://dev/test-report/{tail}")
    assert _refusal_text(str(info.value))
    assert str(tmp_path) not in str(info.value)


def test_name_for_a_directory_is_refused(tree: tuple[DevHarness, Path]) -> None:
    env, repo = tree
    (repo / "docs" / "adr" / "0006-dir.md").mkdir()
    with pytest.raises(ResourceError, match="no such document"):
        env.read("tl://dev/adr/0006-dir")
    assert _index(env, ADR_INDEX) == []


def test_suffix_included_is_not_found(tree: tuple[DevHarness, Path]) -> None:
    env, repo = tree
    (repo / "docs" / "adr" / "0007-real.md").write_text("# Real\n", encoding="utf-8")
    assert env.read("tl://dev/adr/0007-real") == "# Real\n"
    with pytest.raises(ResourceError, match="no such document"):
        env.read("tl://dev/adr/0007-real.md")


def test_symlink_leaving_the_directory_is_refused(tree: tuple[DevHarness, Path]) -> None:
    env, repo = tree
    secret = repo.parent / "outside-secret.txt"
    secret.write_text("TOP SECRET\n", encoding="utf-8")
    link = repo / "docs" / "adr" / "0008-link.md"
    os.symlink(secret, link)
    with pytest.raises(ResourceError) as info:
        env.read("tl://dev/adr/0008-link")
    assert "TOP SECRET" not in str(info.value)
    assert all(str(e["name"]) != "0008-link" for e in _index(env, ADR_INDEX))


def test_symlink_leaving_the_reports_directory_is_refused(tree: tuple[DevHarness, Path]) -> None:
    env, repo = tree
    secret = repo.parent / "outside-report.txt"
    secret.write_text("TOP SECRET\n", encoding="utf-8")
    link = repo / "dev" / "data" / "test-reports" / "20261010T120000Z-ab12cd.txt"
    os.symlink(secret, link)
    with pytest.raises(ResourceError, match="no such document"):
        env.read("tl://dev/test-report/20261010T120000Z-ab12cd.txt")
    assert _index(env, REPORT_INDEX) == []


# --- size and texts ------------------------------------------------------------------------------


def test_document_larger_than_one_mib_is_cut(tree: tuple[DevHarness, Path]) -> None:
    env, repo = tree
    (repo / "docs" / "adr" / "0009-big.md").write_bytes(b"a" * (MAX_BYTES + 500))
    text = env.read("tl://dev/adr/0009-big")
    assert text == "a" * MAX_BYTES + "\n... (cut)\n"
    assert text.rstrip().endswith("... (cut)")


def test_document_at_one_mib_is_not_cut(tree: tuple[DevHarness, Path]) -> None:
    env, repo = tree
    (repo / "docs" / "adr" / "0010-exact.md").write_bytes(b"b" * MAX_BYTES)
    assert env.read("tl://dev/adr/0010-exact") == "b" * MAX_BYTES


def test_invalid_utf8_is_replaced(tree: tuple[DevHarness, Path]) -> None:
    env, repo = tree
    (repo / "docs" / "adr" / "0011-bytes.md").write_bytes(b"ok \xff end\n")
    assert env.read("tl://dev/adr/0011-bytes") == "ok � end\n"


def test_no_absolute_path_in_errors_or_texts(tree: tuple[DevHarness, Path], tmp_path: Path) -> None:
    env, repo = tree
    (repo / "docs" / "adr" / "0012-ok.md").write_text(
        "# Ok\n\nStatus: accepted\n", encoding="utf-8"
    )
    (repo / "dev" / "data" / "test-reports" / "20261010T120000Z-ab12cd.txt").write_text(
        "report\n", encoding="utf-8"
    )
    texts = [
        env.read(ADR_INDEX),
        env.read(RUNBOOK_INDEX),
        env.read(REPORT_INDEX),
        env.read("tl://dev/adr/0012-ok"),
        env.read("tl://dev/test-report/20261010T120000Z-ab12cd.txt"),
    ]
    for uri in (
        "tl://dev/adr/missing",
        "tl://dev/adr/../../etc/passwd",
        "tl://dev/runbook/missing",
        "tl://dev/test-report/missing.txt",
        "tl://dev/test-report/..",
    ):
        with pytest.raises(ResourceError) as info:
            env.read(uri)
        texts.append(str(info.value))
    for text in texts:
        assert str(tmp_path) not in text
        assert str(repo) not in text

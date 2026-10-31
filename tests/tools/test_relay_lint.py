"""``dev/relay-lint``: the relay block validator (P2-W0 brief A3).

The script reads a supervisor reply (stdin or a file) and checks the Code 92 relay block at its end.
These tests run it from the repository root on three clean blocks (states 19, 88 and 2) and on one
broken variant per rule (1 to 6, and 7 for a model name in prose), and pin the exact output lines
and exit codes. Each rule prints at most one line, so a variant that breaks one rule prints one.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "dev" / "relay-lint"
PROVIDED = ROOT / "docs" / "tickets" / "P2-W0" / "provided"

HEADER_19 = "19 P2-W0 r1 base@0a69e0a ck0 g- st@8c87aab C0"
HEADER_88 = "88 P2-W0 r1 base@0a69e0a ck0 g- st@8c87aab C0"
HEADER_2 = "2 P2-W0 r1 base@0a69e0a ck0 g- st@8c87aab C0"
ITEM = "T01 docs/tickets/P2-W0/T01-state-sh.md p2/w0-t01-state-sh t l"
NOTE = "NOTE acc: just check"


def block(
    header: str = HEADER_19,
    items: tuple[str, ...] = (ITEM,),
    markers: tuple[str, ...] = ("95 none", "9 none", "4 none"),
    report: str = "REPORT none",
    note: str = NOTE,
    last: str = "30",
    prose: tuple[str, ...] = ("Prose line one.",),
    after: tuple[str, ...] = (),
) -> str:
    """A relay reply: prose, the block between the markers, then any trailing text."""
    body = [*prose, "=== RELAY ===", header, *items, *markers, report, note]
    if last:
        body.append(last)
    body.append("=== END ===")
    body.extend(after)
    return "\n".join(body) + "\n"


def run(text: str | None = None, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        input=text,
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (block(), "OK 19 P2-W0 r1 1 items"),
        (
            block(
                header=HEADER_88,
                items=(),
                report="REPORT README.md",
            ),
            "OK 88 P2-W0 r1 0 items",
        ),
        (block(header=HEADER_2, items=()), "OK 2 P2-W0 r1 0 items"),
    ],
    ids=["state-19", "state-88", "state-2"],
)
def test_clean_blocks_print_one_ok_line(text: str, expected: str) -> None:
    result = run(text)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [expected]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Rule 1: text after the block (the block must be the last thing in the reply).
        (block(after=("Thanks.",)), "E1 12 text after === END ==="),
        # Rule 2: more than 8 lines of prose before the block.
        (
            block(prose=tuple(f"Prose {i}." for i in range(9))),
            "E2 10 prose before the block exceeds 8 lines",
        ),
        # Rule 3: the header is missing its C<n> field.
        (
            block(header="19 P2-W0 r1 base@0a69e0a ck0 g- st@8c87aab"),
            "E3 3 first line of the block is not a relay header",
        ),
        # Rule 4: a state 19 item whose path does not exist.
        (
            block(items=("T01 docs/tickets/P2-W0/NOPE.md p2/w0-t01-state-sh t l",)),
            "E4 4 item path does not exist",
        ),
        # Rule 5: the 4 line is missing.
        (
            block(markers=("95 none", "9 none")),
            "E5 10 expected one 95, 9, 4, REPORT and NOTE line each, in that order",
        ),
        # Rule 6: the line before === END === is not 30.
        (block(last=""), "E6 9 line before === END === is not 30"),
        # Rule 7: a model name in prose, outside the NOTE line.
        (block(prose=("Built with Claude.",)), "E7 1 model name outside the NOTE line"),
    ],
    ids=["rule-1", "rule-2", "rule-3", "rule-4", "rule-5", "rule-6", "rule-7"],
)
def test_each_broken_rule_prints_one_line(text: str, expected: str) -> None:
    result = run(text)
    assert result.returncode == 1
    assert result.stdout.splitlines() == [expected]


def test_state_88_report_must_name_an_existing_file() -> None:
    text = block(header=HEADER_88, items=(), report="REPORT docs/does-not-exist.md")
    result = run(text)
    assert result.returncode == 1
    assert result.stdout.splitlines() == ["E5 7 REPORT names no existing file"]


def test_provided_ok_file_passes() -> None:
    result = run(None, str(PROVIDED / "relay-ok.txt"))
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["OK 19 P2-W0 r1 1 items"]


def test_provided_bad_file_fails_rule_6() -> None:
    result = run(None, str(PROVIDED / "relay-bad.txt"))
    assert result.returncode == 1
    lines = result.stdout.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("E6 ")


def test_stdin_and_file_give_the_same_output() -> None:
    text = (PROVIDED / "relay-ok.txt").read_text(encoding="utf-8")
    assert run(text).stdout == run(None, str(PROVIDED / "relay-ok.txt")).stdout


@pytest.mark.parametrize(
    "args",
    [
        ("a.txt", "b.txt"),
        ("does-not-exist.txt",),
    ],
    ids=["too-many-args", "missing-file"],
)
def test_bad_usage_exits_2(args: tuple[str, ...]) -> None:
    result = run(None, *args)
    assert result.returncode == 2

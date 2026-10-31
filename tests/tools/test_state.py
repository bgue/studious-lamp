"""dev/state.sh prints one increment's state in at most 40 lines (P2-W0 ticket A1).

Each test builds a fixture git repository in tmp_path (no network), writes a STATE.md into it, and
runs the real script with its working directory inside that repository and WT_ROOT pointing at a
temp directory. The tests are written for the end-of-increment run; they are not run per piece.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "dev" / "state.sh"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
}
HEADER = "# P9-X1 STATE  r=1 base={base} C=C0 ck=- gate=n/a wt=/home/user/wt/p9-x1"
SUBJECT_3 = "P9-X1: third commit, with a subject long enough that it has to be cut at sixty"
BOARD_LINES = ["X1-A p disp f - first board line", "X1-B t todo l - second board line"]
NEXT_LINE = "1. Merge the first ticket branch once its reviewer verdict is in."


@dataclass
class Fixture:
    repo: Path
    wt_root: Path
    header: str
    base: str  # short sha of the first commit, which is also the STATE.md base=
    mid: str  # short sha of the second commit
    tip: str  # short sha of p9/x1 HEAD
    t02: str  # short sha of the one ticket branch that is not merged
    wt_a: Path  # the worktree under WT_ROOT, on p9/x1-t01-a, with an untracked file


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env={**os.environ, **GIT_ENV},
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def short(repo: Path, ref: str) -> str:
    return git(repo, "rev-parse", "--short=7", ref)


def commit(repo: Path, subject: str) -> None:
    git(repo, "commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", subject)


def state_text(base: str, board: list[str], nxt: list[str]) -> str:
    lines = [
        HEADER.format(base=base),
        "## BOARD",
        *board,
        "",
        "## DEC",
        "D1 a decision that must not be printed",
        "",
        "## OPEN",
        "Q1 an open question that must not be printed",
        "",
        "## NEXT",
        *nxt,
        "",
        "## REFS",
        "none",
        "",
    ]
    return "\n".join(lines)


def write_state(repo: Path, text: str) -> None:
    path = repo / "docs" / "tickets" / "P9-X1" / "STATE.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_fixture(tmp_path: Path) -> Fixture:
    base_dir = tmp_path.resolve()
    repo = base_dir / "repo"
    repo.mkdir()
    wt_root = base_dir / "wt"
    wt_root.mkdir()

    git(repo, "init", "-q", "-b", "p9/x1")
    commit(repo, "P9-X1: first commit")
    base = short(repo, "HEAD")
    commit(repo, "P9-X1: second commit")
    mid = short(repo, "HEAD")
    commit(repo, SUBJECT_3)
    tip = short(repo, "HEAD")

    # Merged: points at the tip of p9/x1, so it is an ancestor of the increment branch.
    git(repo, "branch", "p9/x1-t01-a")
    # Unmerged: one commit on top of the base that is not on p9/x1.
    git(repo, "checkout", "-q", "-b", "p9/x1-t02-b", base)
    commit(repo, "P9-X1: ticket b work")
    t02 = short(repo, "HEAD")
    git(repo, "checkout", "-q", "p9/x1")

    wt_a = wt_root / "x1-a"
    git(repo, "worktree", "add", "-q", str(wt_a), "p9/x1-t01-a")
    (wt_a / "scratch.txt").write_text("uncommitted\n", encoding="utf-8")
    # A detached worktree outside WT_ROOT: must not appear in WT.
    git(repo, "worktree", "add", "-q", "--detach", str(base_dir / "elsewhere"))

    write_state(repo, state_text(base, BOARD_LINES, [NEXT_LINE]))
    return Fixture(
        repo=repo,
        wt_root=wt_root,
        header=HEADER.format(base=base),
        base=base,
        mid=mid,
        tip=tip,
        t02=t02,
        wt_a=wt_a,
    )


def run_state(cwd: Path, wt_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "WT_ROOT": str(wt_root)}
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_prints_the_header_and_five_sections_in_order(tmp_path: Path) -> None:
    fx = build_fixture(tmp_path)
    result = run_state(fx.repo, fx.wt_root, "P9-X1")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines == [
        fx.header,
        "BOARD",
        *BOARD_LINES,
        "LOG",
        f"{fx.tip} {SUBJECT_3[:60]}",
        f"{fx.mid} P9-X1: second commit",
        "WT",
        f"{fx.wt_a} p9/x1-t01-a {fx.tip} dirty",
        "HEADS",
        f"p9/x1-t02-b {fx.t02}",
        "NEXT",
        NEXT_LINE,
    ]
    assert len(lines) <= 40


def test_explicit_base_argument_overrides_the_header_base(tmp_path: Path) -> None:
    fx = build_fixture(tmp_path)
    result = run_state(fx.repo, fx.wt_root, "P9-X1", fx.mid)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    log = lines[lines.index("LOG") + 1 : lines.index("WT")]
    assert log == [f"{fx.tip} {SUBJECT_3[:60]}"]


def test_missing_state_md_prints_state_none_and_exits_1(tmp_path: Path) -> None:
    fx = build_fixture(tmp_path)
    result = run_state(fx.repo, fx.wt_root, "NOPE")
    assert result.stdout == "STATE none\n"
    assert result.returncode == 1


def test_no_increment_id_is_bad_usage(tmp_path: Path) -> None:
    fx = build_fixture(tmp_path)
    result = run_state(fx.repo, fx.wt_root)
    assert result.returncode == 2
    assert result.stdout == ""


def test_more_than_fifteen_board_lines_are_cut_with_a_more_marker(tmp_path: Path) -> None:
    fx = build_fixture(tmp_path)
    board = [f"X{i:02d} p todo f - board line {i}" for i in range(1, 18)]
    write_state(fx.repo, state_text(fx.base, board, [NEXT_LINE]))
    result = run_state(fx.repo, fx.wt_root, "P9-X1")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[1] == "BOARD"
    assert lines[2:17] == board[:15]
    assert lines[17] == "+2 more"
    assert lines[18] == "LOG"


def test_output_is_at_most_forty_lines_and_lines_at_most_160_characters(tmp_path: Path) -> None:
    fx = build_fixture(tmp_path)
    board = [f"X{i:02d} p todo f - board line {i}" for i in range(1, 18)]
    long_next = "2. " + "x" * 200
    write_state(fx.repo, state_text(fx.base, board, [NEXT_LINE, long_next]))
    result = run_state(fx.repo, fx.wt_root, "P9-X1")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) <= 40
    assert max(len(line) for line in lines) <= 160
    assert lines[-1] == long_next[:160]


def test_heads_are_capped_at_four_lines_with_a_more_marker(tmp_path: Path) -> None:
    fx = build_fixture(tmp_path)
    # Five more unmerged ticket branches on top of the one in the fixture: six in all.
    for i in range(1, 6):
        git(fx.repo, "branch", f"p9/x1-t1{i}-c", fx.t02)
    result = run_state(fx.repo, fx.wt_root, "P9-X1")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    heads = lines[lines.index("HEADS") + 1 : lines.index("NEXT")]
    assert len(heads) == 5
    assert heads[-1] == "+2 more"


def test_next_is_capped_at_six_lines_with_a_more_marker(tmp_path: Path) -> None:
    fx = build_fixture(tmp_path)
    nxt = [f"{i}. next line {i}" for i in range(1, 9)]
    write_state(fx.repo, state_text(fx.base, BOARD_LINES, nxt))
    result = run_state(fx.repo, fx.wt_root, "P9-X1")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[lines.index("NEXT") + 1 :] == [*nxt[:6], "+2 more"]


def test_output_over_forty_lines_is_cut_and_ends_with_a_more_lines_marker(tmp_path: Path) -> None:
    fx = build_fixture(tmp_path)
    # LOG: 12 commits since base, cut to 10. BOARD: 17 lines, cut to 15 plus "+2 more".
    for i in range(10):
        commit(fx.repo, f"P9-X1: extra commit {i}")
    for i in range(1, 6):
        git(fx.repo, "branch", f"p9/x1-t1{i}-c", fx.t02)
    board = [f"X{i:02d} p todo f - board line {i}" for i in range(1, 18)]
    nxt = [f"{i}. next line {i}" for i in range(1, 9)]
    write_state(fx.repo, state_text(fx.base, board, nxt))
    result = run_state(fx.repo, fx.wt_root, "P9-X1")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    # Uncut total: 1 header + 17 BOARD + 11 LOG + 2 WT + 6 HEADS + 8 NEXT = 45 lines.
    assert len(lines) == 40
    assert lines[0] == fx.header
    assert lines[-1] == "+6 more lines"

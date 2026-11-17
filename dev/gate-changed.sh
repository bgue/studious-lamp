#!/usr/bin/env bash
# Fast gate for the files a branch changed (process-v3 rules 7 and 8, V3-P2). Steps, stopping at the first red,
# each printing one line (full output of the test steps goes to .gate/changed-<step>.log):
#   ruff      ruff check and ruff format --check on the changed .py files
#   pyright   pyright on the changed .py files
#   commit    dev/commit-check.sh <base> (model names outside trailers, and in docs/reports)
#   tests     bash dev/gate.sh <paths>: the tests dir of each touched package (packages/<p>/tests,
#             packages/tl-modules/<m>/tests), each touched tests/<x> dir, and the confidentiality walk set
#             (the tests that use twin_channels, tests/confidentiality/test_*walk*.py, test_hidden_sql_equal_old.py,
#             test_paths_equal_old.py)
#   gate-pg   bash dev/gate.sh --postgres tests/confidentiality, only when the diff touches packages/tl-adapters/,
#             packages/tl-core/src/tl_core/confidentiality.py or a projectors/ path
#   perf      bash dev/gate.sh tests/perf, when tests/perf exists
# The test steps take flock /tmp/claude-0/tl-gate.lock, so two worktrees never run a heavy step at once.
#
# Usage: dev/gate-changed.sh [--dry-run] [BASE]
#   BASE        a ref or sha (default: git merge-base HEAD p2/v3-forms, else origin/claude/wizardly-allen-m2v96s)
#   --dry-run   print the plan (steps and paths) and run nothing
# Changed files: committed and uncommitted changes against BASE, plus untracked files that are not ignored.
# Last line: gate: PASS, gate: FAIL, or gate: DRY-RUN. Exit 0 only on PASS.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 2

usage() {
  echo "usage: dev/gate-changed.sh [--dry-run] [BASE]" >&2
  exit 2
}

dry=0
base=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) dry=1; shift ;;
    -h|--help) usage ;;
    -*) echo "gate-changed: unknown option: $1" >&2; usage ;;
    *)
      [ -z "$base" ] || usage
      base="$1"; shift ;;
  esac
done

base_note="given"
if [ -z "$base" ]; then
  if merged="$(git merge-base HEAD p2/v3-forms 2>/dev/null)"; then
    base="$merged"
    base_note="merge-base with p2/v3-forms"
  else
    base="origin/claude/wizardly-allen-m2v96s"
    base_note="fallback"
  fi
fi
if ! base_sha="$(git rev-parse --verify -q "$base^{commit}")"; then
  echo "gate-changed: base not found: $base" >&2
  exit 2
fi
base_short="$(git rev-parse --short=7 "$base_sha")"

# Changed files (sorted, unique), existing or deleted.
mapfile -t files < <({ git diff --name-only --no-renames "$base_sha"; git ls-files --others --exclude-standard; } \
  | sed '/^$/d' | sort -u)

py=()
dirs=()
pg=0
for f in "${files[@]}"; do
  case "$f" in
    *.py) if [ -f "$f" ]; then py+=("$f"); fi ;;
  esac
  if [[ "$f" == packages/tl-modules/* ]]; then
    rest="${f#packages/tl-modules/}"
    d="packages/tl-modules/${rest%%/*}/tests"
  elif [[ "$f" == packages/* ]]; then
    rest="${f#packages/}"
    d="packages/${rest%%/*}/tests"
  elif [[ "$f" == tests/*/* ]]; then
    rest="${f#tests/}"
    d="tests/${rest%%/*}"
  else
    d=""
  fi
  if [ -n "$d" ] && [ -d "$d" ]; then
    dirs+=("$d")
  fi
  case "$f" in
    packages/tl-adapters/*|packages/tl-core/src/tl_core/confidentiality.py|*projectors/*) pg=1 ;;
  esac
done

# The confidentiality walk set: every test file that uses twin_channels, plus the named files.
walk=()
while IFS= read -r t; do
  walk+=("$t")
done < <(grep -rlE --include='test_*.py' 'twin_channels' tests packages 2>/dev/null | sort || true)
for t in tests/confidentiality/test_*walk*.py tests/confidentiality/test_hidden_sql_equal_old.py \
    tests/confidentiality/test_paths_equal_old.py; do
  if [ -f "$t" ]; then
    walk+=("$t")
  fi
done

# Test targets: the dirs, then the walk files not already inside one of them (sorted, unique).
targets=()
mapfile -t all_targets < <({ printf '%s\n' "${dirs[@]}"; printf '%s\n' "${walk[@]}"; } \
  | sed '/^$/d' | sort -u)
for t in "${all_targets[@]}"; do
  covered=0
  for d in "${dirs[@]}"; do
    if [ "$t" = "$d" ] || [[ "$t" == "$d"/* ]]; then
      covered=1
      break
    fi
  done
  if [ "$covered" -eq 0 ]; then
    targets+=("$t")
  fi
done
mapfile -t test_paths < <({ printf '%s\n' "${dirs[@]}"; printf '%s\n' "${targets[@]}"; } \
  | sed '/^$/d' | sort -u)

lock=/tmp/claude-0/tl-gate.lock
ruff_do() { uv run ruff check "$@" && uv run ruff format --check "$@"; }

if [ "$dry" -eq 1 ]; then
  echo "gate-changed: base $base_short ($base_note)"
  echo "changed: ${#files[@]} files, ${#py[@]} .py"
  if [ ${#py[@]} -gt 0 ]; then
    echo "plan ruff: ruff check, ruff format --check ${py[*]}"
    echo "plan pyright: ${py[*]}"
  else
    echo "plan ruff: skip (no changed .py files)"
    echo "plan pyright: skip (no changed .py files)"
  fi
  echo "plan commit: dev/commit-check.sh $base_short"
  if [ ${#test_paths[@]} -gt 0 ]; then
    echo "plan tests: flock $lock bash dev/gate.sh ${test_paths[*]}"
  else
    echo "plan tests: skip (no test paths)"
  fi
  if [ "$pg" -eq 1 ]; then
    echo "plan gate-pg: flock $lock bash dev/gate.sh --postgres tests/confidentiality"
  else
    echo "plan gate-pg: skip (no adapter, confidentiality or projector path)"
  fi
  if [ -d tests/perf ]; then
    echo "plan perf: flock $lock bash dev/gate.sh tests/perf"
  else
    echo "plan perf: skip (no tests/perf)"
  fi
  echo "gate: DRY-RUN"
  exit 0
fi

mkdir -p .gate "$(dirname "$lock")"

# step_fail <step> <detail>: prints the step line, the first failing test lines, and gate: FAIL; exits 1.
step_fail() {
  echo "$1: FAIL $2"
  if [ -f ".gate/changed-$1.log" ]; then
    grep -E '^(FAILED|ERROR) ' ".gate/changed-$1.log" | head -n 20 | cut -c1-160 || true
  fi
  echo "gate: FAIL"
  exit 1
}

if [ ${#py[@]} -gt 0 ]; then
  if ruff_do "${py[@]}" >".gate/changed-ruff.log" 2>&1; then
    echo "ruff: PASS ${#py[@]} files"
  else
    step_fail ruff "(see .gate/changed-ruff.log)"
  fi
  if uv run pyright "${py[@]}" >".gate/changed-pyright.log" 2>&1; then
    echo "pyright: PASS ${#py[@]} files"
  else
    step_fail pyright "(see .gate/changed-pyright.log)"
  fi
else
  echo "ruff: SKIP no changed .py files"
  echo "pyright: SKIP no changed .py files"
fi

if bash dev/commit-check.sh "$base_sha" >".gate/changed-commit.log" 2>&1; then
  echo "commit: PASS $base_short..HEAD"
else
  cat ".gate/changed-commit.log"
  step_fail commit "(model names above)"
fi

run_gate() { # <step> <gate.sh arguments...>
  local name="$1"; shift
  if flock "$lock" bash dev/gate.sh "$@" >".gate/changed-$name.log" 2>&1; then
    echo "$name: PASS $(grep -E '^part ' ".gate/changed-$name.log" | tail -n 1 | cut -c1-120 || true)"
  else
    step_fail "$name" "exit $? (see .gate/changed-$name.log)"
  fi
}

if [ ${#test_paths[@]} -gt 0 ]; then
  run_gate tests "${test_paths[@]}"
else
  echo "tests: SKIP no test paths"
fi

if [ "$pg" -eq 1 ]; then
  run_gate gate-pg --postgres tests/confidentiality
else
  echo "gate-pg: SKIP no adapter, confidentiality or projector path"
fi

if [ -d tests/perf ]; then
  run_gate perf tests/perf
else
  echo "perf: SKIP no tests/perf"
fi

echo "gate: PASS"
exit 0

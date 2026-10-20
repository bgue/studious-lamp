#!/usr/bin/env bash
# Deterministic test gate. Runs the suite in sequential parts (one pytest session at a time, never in
# parallel), writes each part's full output to .gate/<part>.log, and prints a compact summary.
#
# Usage: dev/gate.sh [--postgres] [--parts N] [PATHS...]
#   no PATHS    the whole suite, split into N parts (default 4) of roughly equal test-directory count
#   PATHS       only those test paths (relative to the repo root), run as one part
#   --postgres  also run the parity suite on Postgres (--adapters sqlite,postgres); exits 3 if not ready
# Exit 0 only if every part exits 0 (pytest exit 5, no tests collected, counts as a pass).
set -u

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 2

usage() {
  echo "usage: dev/gate.sh [--postgres] [--parts N] [PATHS...]" >&2
  exit 2
}

postgres=0
parts=4
paths=()
while [ $# -gt 0 ]; do
  case "$1" in
    --postgres) postgres=1; shift ;;
    --parts) [ $# -ge 2 ] || usage; parts="$2"; shift 2 ;;
    --parts=*) parts="${1#--parts=}"; shift ;;
    -h|--help) usage ;;
    --) shift; paths+=("$@"); break ;;
    -*) echo "gate: unknown option: $1" >&2; usage ;;
    *) paths+=("$1"); shift ;;
  esac
done
case "$parts" in
  ''|*[!0-9]*|0) echo "gate: --parts needs a positive integer, got '$parts'" >&2; exit 2 ;;
esac

if [ "$postgres" -eq 1 ]; then
  if ! pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
    echo "postgres: not ready"
    exit 3
  fi
  export TL_REQUIRE_POSTGRES=1
  export TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test
fi

if [ ${#paths[@]} -gt 0 ]; then
  targets=("${paths[@]}")
  parts=1
else
  mapfile -t targets < <(ls -d packages/*/tests packages/tl-modules/*/tests tests/*/ 2>/dev/null | sed 's:/*$::')
  if [ ${#targets[@]} -eq 0 ]; then
    echo "gate: no test directories found" >&2
    exit 2
  fi
  if [ "$parts" -gt "${#targets[@]}" ]; then
    parts=${#targets[@]}
  fi
fi

total=${#targets[@]}
mkdir -p .gate
part_rc=()
part_summary=()
failures=()
verdict=0

for ((k = 1; k <= parts; k++)); do
  start=$(( (k - 1) * total / parts ))
  end=$(( k * total / parts ))
  part_targets=("${targets[@]:start:end-start}")
  name="part-$k"
  log=".gate/$name.log"
  bt="/tmp/pt-gate-$$-$name"
  extra=()
  if [ "$postgres" -eq 1 ]; then
    extra=(--adapters sqlite,postgres)
  fi

  uv run pytest -q -p no:cacheprovider --tb=line -rfE --basetemp="$bt" \
    ${extra[@]+"${extra[@]}"} "${part_targets[@]}" >"$log" 2>&1
  rc=$?
  rm -rf -- "$bt"

  summary="$(grep -E '^(=+ )?([0-9]+ [a-z]|no tests ran)[^=]* in [0-9.]+s' "$log" | tail -n 1 \
    | sed -E 's/^=+ *//; s/ *=+ *$//')"
  if [ -z "$summary" ]; then
    summary="no pytest summary line (see $log)"
  fi

  part_rc+=("$rc")
  part_summary+=("$summary")
  while IFS= read -r line; do
    failures+=("$(printf '%s' "$line" | cut -c1-160)")
  done < <(grep -E '^(FAILED|ERROR) ' "$log")
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 5 ]; then
    verdict=1
  fi
done

for ((k = 1; k <= parts; k++)); do
  echo "part $k: exit ${part_rc[k-1]}, ${part_summary[k-1]}"
done

nfail=${#failures[@]}
if [ "$nfail" -gt 40 ]; then
  for ((i = 0; i < 39; i++)); do
    echo "${failures[i]}"
  done
  echo "... $((nfail - 39)) more FAILED/ERROR lines in .gate/*.log"
else
  for ((i = 0; i < nfail; i++)); do
    echo "${failures[i]}"
  done
fi

if [ "$verdict" -eq 0 ]; then
  echo "gate: PASS"
  exit 0
fi
echo "gate: FAIL"
exit 1

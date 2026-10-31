#!/usr/bin/env bash
# dev/review-pack.sh: one call that prints what a reviewer needs from a ticket branch (P2-W0, ticket A2).
#
# Usage: bash dev/review-pack.sh <base> <branch> [<ticket path>]
#
# Sections, in this order, each opened by a line holding only its name: DIFFSTAT, SYMBOLS, PATHS,
# TESTS, COMMITS, GATE. At most 60 lines. Exit 0 when there is no finding; 1 on a finding (a PATHS
# entry, a missing test or a `cmp differs`, a BAD-MSG or a MODEL-NAME); 2 on bad usage. Reads git
# objects and the branch worktree's .gate/summary.txt only; no network, no Python.
#
# Without a ticket path the ticket is found on the branch as docs/tickets/<INC>/<ID>-*.md: the branch
# p2/w0-t01-x gives INC P2-W0 and ID T01. Allowed paths are the backticked items in the bullets under
# "## Allowed paths"; Tests to add is the first backticked item of each bullet under "## Tests to add",
# and `a` -> `b` pairs in such a bullet are provided-test mappings (cmp a with b). The report path
# docs/reports/<INC>/<id>.md is always allowed.
#
# SYMBOLS is a heuristic, not a parser: a def or class extends over the following lines indented deeper
# than it (blank and comment lines do not end it). A `git diff -U0` hunk is attributed to the innermost
# block it touches (old side for removed lines, new side for added ones) and every enclosing block counts
# as touched. A flush-left line inside a multi-line string can end a block early.
set -euo pipefail

usage() {
  echo "usage: dev/review-pack.sh <base> <branch> [<ticket path>]" >&2
  exit 2
}

[ "$#" -ge 2 ] && [ "$#" -le 3 ] || usage
base="$1"
branch_arg="$2"
ticket_arg="${3:-}"
git rev-parse --verify -q "$base^{commit}" >/dev/null || { echo "review-pack: not a commit: $base" >&2; exit 2; }
git rev-parse --verify -q "$branch_arg^{commit}" >/dev/null || { echo "review-pack: not a commit: $branch_arg" >&2; exit 2; }

branch="$(git symbolic-ref -q --short "$branch_arg" 2>/dev/null || printf '%s' "$branch_arg")"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# awk programs (mawk and gawk compatible; no network, no extra tools)

# Tickets: "A<TAB>pattern" for Allowed paths, "T<TAB>path" for Tests to add, "M<TAB>src<TAB>dst" for mappings.
read -r -d '' TICKET_AWK <<'AWK' || true
function items(s, arr,   n) {
  n = 0
  while (match(s, /`[^`]+`/)) {
    n++
    arr[n] = substr(s, RSTART + 1, RLENGTH - 2)
    s = substr(s, RSTART + RLENGTH)
  }
  return n
}
/^## / { sec = $0; next }
/^- / && sec == "## Allowed paths" {
  n = items($0, arr)
  for (i = 1; i <= n; i++) print "A\t" arr[i]
  next
}
/^- / && sec == "## Tests to add" {
  rest = $0
  maps = 0
  while (match(rest, /`[^`]+` -> `[^`]+`/)) {
    pair = substr(rest, RSTART, RLENGTH)
    rest = substr(rest, RSTART + RLENGTH)
    gsub(/`/, "", pair)
    split(pair, pr, " -> ")
    print "M\t" pr[1] "\t" pr[2]
    print "T\t" pr[2]
    maps++
  }
  if (maps == 0) {
    n = items($0, arr)
    if (n > 0) print "T\t" arr[1]
  }
  next
}
AWK

# Symbols, one side: "<side> L <line> <qualified name>" for every line inside a def or class (the
# def line itself included, blank lines included), and "<side> D <qualified name>" for each def or class.
read -r -d '' SYM_AWK <<'AWK' || true
function qual(   i, s) {
  s = ""
  for (i = 1; i <= n; i++) s = (i == 1) ? names[i] : s "." names[i]
  return s
}
BEGIN { n = 0 }
/^[[:blank:]]*$/ || /^[[:blank:]]*#/ { if (n > 0) print side, "L", FNR, qual(); next }
/^[[:blank:]]*(async[[:blank:]]+)?(def|class)[[:blank:]]+[A-Za-z_]/ {
  match($0, /^[[:blank:]]*/); ind = RLENGTH
  t = $0
  sub(/^[[:blank:]]*(async[[:blank:]]+)?(def|class)[[:blank:]]+/, "", t)
  match(t, /^[A-Za-z_][A-Za-z0-9_]*/)
  while (n > 0 && ind_s[n] >= ind) n--
  n++
  names[n] = substr(t, 1, RLENGTH)
  ind_s[n] = ind
  print side, "L", FNR, qual()
  print side, "D", qual()
  next
}
{
  match($0, /^[[:blank:]]*/); ind = RLENGTH
  while (n > 0 && ind_s[n] >= ind) n--
  if (n > 0) print side, "L", FNR, qual()
}
AWK

# Hunks of a `git diff -U0` for one file: "H <old start> <old count> <new start> <new count>".
read -r -d '' HUNK_AWK <<'AWK' || true
/^@@ / {
  split($2, o, ",")
  split($3, w, ",")
  a = substr(o[1], 2) + 0
  b = (o[2] == "") ? 1 : o[2] + 0
  c = substr(w[1], 2) + 0
  d = (w[2] == "") ? 1 : w[2] + 0
  print "H", a, b, c, d
}
AWK

# Classification: "+ name" added, "- name" removed, "~ name" body touched (ancestors included).
read -r -d '' CLS_AWK <<'AWK' || true
function mark(arr, q,   parts, m, k, s) {
  arr[q] = 1
  m = split(q, parts, ".")
  s = ""
  for (k = 1; k < m; k++) {
    s = (k == 1) ? parts[1] : s "." parts[k]
    arr[s] = 1
  }
}
$1 == "H" { nh++; ha[nh] = $2 + 0; hb[nh] = $3 + 0; hc[nh] = $4 + 0; hd[nh] = $5 + 0; next }
$1 == "O" && $2 == "L" { oq[$3 + 0] = $4; next }
$1 == "N" && $2 == "L" { nq[$3 + 0] = $4; next }
$1 == "O" && $2 == "D" { od[$3] = 1; next }
$1 == "N" && $2 == "D" { nd[$3] = 1; next }
END {
  for (h = 1; h <= nh; h++) {
    for (i = ha[h]; i < ha[h] + hb[h]; i++) if (i in oq) mark(tc, oq[i])
    for (i = hc[h]; i < hc[h] + hd[h]; i++) if (i in nq) mark(tc, nq[i])
  }
  for (q in nd) if (!(q in od)) print "+", q
  for (q in od) if (!(q in nd)) print "-", q
  for (q in tc) if ((q in od) && (q in nd)) print "~", q
}
AWK

# ---------------------------------------------------------------------------------------------------
# output buffer: every line goes through emit and is cut to 160 characters at the end

OUT=()
finding=0
emit() { OUT+=("$1"); }

# emit_list CAP ITEM...: at most CAP items, then "... N more" when cut
emit_list() {
  local cap="$1" k=0 item
  shift
  for item in "$@"; do
    k=$((k + 1))
    if [ "$k" -gt "$cap" ]; then
      emit "... $(( $# - cap )) more"
      return 0
    fi
    emit "$item"
  done
}

# ---------------------------------------------------------------------------------------------------
# ticket

# find_ticket: prints docs/tickets/<INC>/<ID>-*.md as it is on the branch, or nothing
find_ticket() {
  local first rest s1 s2 inc tid f
  case "$branch" in
    */*) ;;
    *) return 0 ;;
  esac
  first="${branch%%/*}"
  rest="${branch#*/}"
  IFS=- read -r s1 s2 _ <<<"$rest" || true
  if [ -z "${s1:-}" ] || [ -z "${s2:-}" ]; then
    return 0
  fi
  inc="${first^^}-${s1^^}"
  tid="${s2^^}"
  while IFS= read -r f; do
    case "$f" in
      "docs/tickets/$inc/$tid"-*.md)
        printf '%s\n' "$f"
        return 0
        ;;
    esac
  done < <(git ls-tree -r --name-only "$branch_arg" -- "docs/tickets/$inc/" 2>/dev/null)
  return 0
}

ticket_path="$ticket_arg"
if [ -z "$ticket_path" ]; then
  ticket_path="$(find_ticket)"
fi

have=0
ticket_text=""
if [ -n "$ticket_path" ] && ticket_text="$(git show "$branch_arg:$ticket_path" 2>/dev/null)"; then
  have=1
fi

inc=""
tid_full=""
short=""
report=""
allowed_pats=()
test_paths=()
map_src=()
map_dst=()
if [ "$have" -eq 1 ]; then
  dir="${ticket_path%/*}"
  inc="${dir##*/}"
  first_line="${ticket_text%%$'\n'*}"
  case "$first_line" in
    "# "*)
      tid_full="${first_line#\# }"
      tid_full="${tid_full%%[[:space:]]*}"
      ;;
  esac
  if [ -n "$tid_full" ]; then
    short="${tid_full#"$inc"-}"
    if [ "$short" = "$tid_full" ]; then
      short="${tid_full##*-}"
    fi
    report="docs/reports/$inc/$short.md"
  fi
  parsed="$(printf '%s\n' "$ticket_text" | awk "$TICKET_AWK")"
  while IFS=$'\t' read -r kind a b; do
    case "$kind" in
      A) allowed_pats+=("$a") ;;
      T) test_paths+=("$a") ;;
      M)
        map_src+=("$a")
        map_dst+=("$b")
        ;;
    esac
  done <<<"$parsed"
fi

# is_allowed PATH: matches the Allowed paths globs or the report path
is_allowed() {
  local p="$1" pat
  if [ -n "$report" ] && [ "$p" = "$report" ]; then
    return 0
  fi
  for pat in "${allowed_pats[@]}"; do
    if [[ "$p" == $pat ]]; then
      return 0
    fi
  done
  return 1
}

# cmp_line SRC DST: "cmp same DST" or "cmp differs DST", both read from the branch tree
cmp_line() {
  local src="$1" dst="$2"
  if git show "$branch_arg:$src" >"$tmp/cmp-src" 2>/dev/null \
    && git show "$branch_arg:$dst" >"$tmp/cmp-dst" 2>/dev/null \
    && cmp -s "$tmp/cmp-src" "$tmp/cmp-dst"; then
    printf 'cmp same %s\n' "$dst"
  else
    printf 'cmp differs %s\n' "$dst"
  fi
}

# model_named BODY: true when a body line outside the trailer names a model word
model_named() {
  local line low tokens word
  while IFS= read -r line; do
    case "$line" in
      "Co-Authored-By:"* | "Claude-Session:"*) continue ;;
    esac
    low="${line,,}"
    tokens=" ${low//[^a-z0-9]/ } "
    for word in opus sonnet haiku claude gpt; do
      case "$tokens" in
        *" $word "*) return 0 ;;
      esac
    done
  done <<<"$1"
  return 1
}

# ---------------------------------------------------------------------------------------------------
# sections

diffstat_section() {
  local -a ds=()
  local n k l
  mapfile -t ds < <(git diff --stat "$base...$branch_arg")
  n=${#ds[@]}
  if [ "$n" -eq 0 ]; then
    emit "none"
    return 0
  fi
  if [ "$n" -le 20 ]; then
    for l in "${ds[@]}"; do
      emit "$l"
    done
    return 0
  fi
  for ((k = 0; k < 18; k++)); do
    emit "${ds[k]}"
  done
  emit "... $((n - 19)) more"
  emit "${ds[n - 1]}"
}

symbols_section() {
  local -a sym=() sorted=()
  local f sign q files
  files="$(git diff --no-renames --name-only "$base...$branch_arg" -- '*.py')"
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    git show "$base:$f" >"$tmp/old.py" 2>/dev/null || : >"$tmp/old.py"
    git show "$branch_arg:$f" >"$tmp/new.py" 2>/dev/null || : >"$tmp/new.py"
    git diff -U0 --no-color --no-renames "$base...$branch_arg" -- "$f" >"$tmp/d.diff" 2>/dev/null \
      || : >"$tmp/d.diff"
    {
      awk -v side=O "$SYM_AWK" "$tmp/old.py"
      awk -v side=N "$SYM_AWK" "$tmp/new.py"
      awk "$HUNK_AWK" "$tmp/d.diff"
    } >"$tmp/map"
    while IFS=' ' read -r sign q; do
      [ -n "$q" ] || continue
      sym+=("$f:$q $sign")
    done < <(awk "$CLS_AWK" "$tmp/map")
  done <<<"$files"
  if [ "${#sym[@]}" -eq 0 ]; then
    emit "none"
    return 0
  fi
  mapfile -t sorted < <(printf '%s\n' "${sym[@]}" | LC_ALL=C sort)
  emit_list 19 "${sorted[@]}"
}

paths_section() {
  if [ "$have" -eq 0 ]; then
    emit "TICKET none"
    return 0
  fi
  local changed p
  local -a outside=()
  changed="$(git diff --no-renames --name-only "$base...$branch_arg")"
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    if ! is_allowed "$p"; then
      outside+=("$p")
    fi
  done <<<"$changed"
  if [ "${#outside[@]}" -eq 0 ]; then
    emit "OK"
    return 0
  fi
  finding=1
  emit_list 4 "${outside[@]}"
}

tests_section() {
  if [ "$have" -eq 0 ]; then
    emit "TICKET none"
    return 0
  fi
  local -A seen=()
  local -a lines=()
  local p i line
  for p in "${test_paths[@]}"; do
    if [ -n "${seen[$p]:-}" ]; then
      continue
    fi
    seen[$p]=1
    if git cat-file -e "$branch_arg:$p" 2>/dev/null; then
      lines+=("$p present")
    else
      lines+=("$p missing")
      finding=1
    fi
  done
  for i in "${!map_src[@]}"; do
    line="$(cmp_line "${map_src[i]}" "${map_dst[i]}")"
    lines+=("$line")
    case "$line" in
      "cmp differs"*) finding=1 ;;
    esac
  done
  if [ "${#lines[@]}" -eq 0 ]; then
    emit "none"
    return 0
  fi
  emit_list 3 "${lines[@]}"
}

commits_section() {
  local -a shas=() flagged=() plain=() show=()
  local sha s7 subj body flags line total
  mapfile -t shas < <(git rev-list --reverse "$base..$branch_arg")
  for sha in "${shas[@]}"; do
    [ -n "$sha" ] || continue
    s7="$(git rev-parse --short=7 "$sha")"
    subj="$(git log -1 --format=%s "$sha")"
    body="$(git log -1 --format=%b "$sha")"
    flags=""
    if [ -n "$tid_full" ] && [[ "$subj" != "$tid_full: "* ]]; then
      flags="BAD-MSG"
    fi
    if model_named "$body"; then
      flags="${flags:+$flags }MODEL-NAME"
    fi
    line="$s7 ${subj:0:100}"
    if [ -n "$flags" ]; then
      finding=1
      flagged+=("$line  $flags")
    else
      plain+=("$line")
    fi
  done
  total=$(( ${#flagged[@]} + ${#plain[@]} ))
  if [ "$total" -eq 0 ]; then
    emit "none"
    return 0
  fi
  show=("${flagged[@]}" "${plain[@]}")
  emit_list 3 "${show[@]}"
}

gate_section() {
  local wt="" gl="g-"
  wt="$(git worktree list --porcelain \
    | awk -v b="refs/heads/$branch" '/^worktree /{p = substr($0, 10)} $0 == "branch " b {f = p} END {if (f != "") print f}')"
  if [ -n "$wt" ] && [ -f "$wt/.gate/summary.txt" ]; then
    gl="$(tail -n 1 "$wt/.gate/summary.txt")"
    [ -n "$gl" ] || gl="g-"
  fi
  emit "$gl"
}

emit "DIFFSTAT"
diffstat_section
emit "SYMBOLS"
symbols_section
emit "PATHS"
paths_section
emit "TESTS"
tests_section
emit "COMMITS"
commits_section
emit "GATE"
gate_section

printf '%s\n' "${OUT[@]}" | cut -c1-160
if [ "$finding" -eq 1 ]; then
  exit 1
fi
exit 0

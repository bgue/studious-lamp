#!/usr/bin/env bash
# One-call increment state for a supervisor or the orchestrator (P2-W0 ticket A1).
#
# Usage: dev/state.sh <INC> [<base>]
#   INC    increment id, e.g. P2-W0. Its branch is the id lower-cased with its first "-" replaced by "/".
#   base   optional ref. Default: the base= token on line 1 of docs/tickets/<INC>/STATE.md, else $TRUNK
#          (default main).
# Output: at most 40 lines, each at most 160 characters. Line 1 is the STATE.md header verbatim, then the
# sections BOARD, LOG, WT, HEADS and NEXT, each opened by a line holding only its name.
# Env: WT_ROOT worktree root (default /home/user/wt); TRUNK fallback base (default main).
# Exit 0 on success, 1 when STATE.md is missing (prints "STATE none"), 2 on bad usage.
set -euo pipefail

usage() {
  echo "usage: dev/state.sh <INC> [<base>]" >&2
  exit 2
}

[ $# -ge 1 ] && [ $# -le 2 ] || usage
inc="$1"
case "$inc" in
  '' | *[!A-Za-z0-9-]*) echo "state: bad increment id '$inc'" >&2; exit 2 ;;
esac

top="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "state: not inside a git repository" >&2
  exit 2
}
cd "$top"

lc="${inc,,}"
incbr="${lc/-/\/}"
state="docs/tickets/$inc/STATE.md"
if [ ! -f "$state" ]; then
  echo "STATE none"
  exit 1
fi

header="$(head -n 1 "$state")"
read -ra words <<< "$header"
hbase=""
for w in "${words[@]}"; do
  case "$w" in base=*) hbase="${w#base=}" ;; esac
done
base="${2:-${hbase:-${TRUNK:-main}}}"
if ! git rev-parse --verify -q "$base^{commit}" >/dev/null; then
  echo "state: base '$base' does not resolve to a commit" >&2
  exit 2
fi

have_inc=0
if git rev-parse --verify -q "refs/heads/$incbr" >/dev/null; then
  have_inc=1
fi

# Non-blank lines under "## <name>" in STATE.md, up to the next "## " heading.
section() {
  awk -v sec="$1" '/^## /{ p = ($2 == sec); next } p && NF { print }' "$state"
}

lines=("$header")

# BOARD: at most 15 lines, then "+n more" when cut.
lines+=("BOARD")
mapfile -t board < <(section BOARD)
for ((i = 0; i < ${#board[@]} && i < 15; i++)); do
  lines+=("${board[i]}")
done
if [ "${#board[@]}" -gt 15 ]; then
  lines+=("+$(( ${#board[@]} - 15 )) more")
fi

# LOG: commits on the increment branch since base, at most 10.
lines+=("LOG")
if [ "$have_inc" -eq 1 ]; then
  while IFS=$'\t' read -r sha subj; do
    lines+=("${sha:0:7} ${subj:0:60}")
  done < <(git log -n 10 --format='%H%x09%s' "$base..$incbr")
else
  lines+=("no branch $incbr")
fi

# WT: open worktrees under the worktree root whose branch starts with the increment branch.
wt_root="${WT_ROOT:-/home/user/wt}"
wt_root="${wt_root%/}"
wt_path=""
wt_br=""
wt_head=""
flush_wt() {
  if [ -n "$wt_path" ] && [[ "$wt_path" == "$wt_root"/* ]] && [[ "$wt_br" == "$incbr"* ]]; then
    st=clean
    if [ -n "$(git -C "$wt_path" status --porcelain 2>/dev/null)" ]; then
      st=dirty
    fi
    lines+=("$wt_path $wt_br ${wt_head:0:7} $st")
  fi
  wt_path=""
  wt_br=""
  wt_head=""
}
lines+=("WT")
while IFS= read -r ln; do
  case "$ln" in
    worktree\ *) flush_wt; wt_path="${ln#worktree }" ;;
    HEAD\ *) wt_head="${ln#HEAD }" ;;
    branch\ refs/heads/*) wt_br="${ln#branch refs/heads/}" ;;
    '') flush_wt ;;
  esac
done < <(git worktree list --porcelain)
flush_wt

# HEADS: ticket branches (<incbr>-*) not merged into the increment branch.
lines+=("HEADS")
if [ "$have_inc" -eq 1 ]; then
  while read -r br sha; do
    [ -n "$br" ] || continue
    if ! git merge-base --is-ancestor "$sha" "$incbr" 2>/dev/null; then
      lines+=("$br ${sha:0:7}")
    fi
  done < <(git branch --list --format='%(refname:short) %(objectname)' "$incbr-*")
fi

# NEXT: the lines under "## NEXT", verbatim.
lines+=("NEXT")
mapfile -t nxt < <(section NEXT)
for l in "${nxt[@]}"; do
  lines+=("$l")
done

for l in "${lines[@]}"; do
  printf '%s\n' "${l:0:160}"
done
exit 0

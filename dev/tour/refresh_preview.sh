#!/usr/bin/env bash
# Re-create the preview branch p2/w1-preview from the current heads of its parts:
#
#     bash dev/tour/refresh_preview.sh [--no-check] [--no-tools]
#
# Run it in the worktree of p2/w1-preview (git worktree add <dir> p2/w1-preview). It saves the
# branch head, resets the branch to `main`, merges p2/i1, p2/i3 and p2/web1 in that order
# ("Merge p2/<x> into p2/w1-preview"), resolves only mechanical conflicts, puts the preview tools
# back (dev/tour/wave1.py, wave1_web.mjs, this script, the `just tour wave1` recipe), regenerates
# what is generated, runs `just check` and leaves the branch at the new head. The old head is kept
# as the tag preview-before-<time> so a refresh can be undone with `git reset --hard <tag>`.
#
# Mechanical conflicts, and what is done with each:
#   uv.lock                                     checkout ours, `uv lock` at the end
#   docs/reference/openapi.json                 checkout ours, `python -m tl_api.openapi` at the end
#   packages/tl-schema/.../generated/**         checkout ours, `just gen` at the end
#   pyproject.toml, packages/*/pyproject.toml   keep both sides' lines (tables, dependency lists)
#   registries and pin lists (tl_api app/commands/errors/auth, tl_mcp server/identity, tl_tui
#   client/embedded, test pins)                 keep both sides' entries; a method that ends in a
#                                               docstring before a shared `...` gets its own `...`
#   a count in a test (`== 37` against `== 39`) base + both changes
# Anything else (a conflict in other code, a delete against an edit) stops the script with exit 3,
# the merge left open for a person to read; nothing is guessed. `--no-check` skips `just check`
# (about four minutes). `--no-tools` leaves the preview tools out (for a test of the merges alone).
# The script does not push: `git push --force-with-lease origin p2/w1-preview`.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
BRANCH=p2/w1-preview
PARTS=(i1 i3 web1)
TRAILER=$'Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4'
CHECK=1
TOOLS=1
for arg in "$@"; do
  case "$arg" in
    --no-check) CHECK=0 ;;
    --no-tools) TOOLS=0 ;;
    *) echo "unknown option $arg" >&2; exit 2 ;;
  esac
done

quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
say() { printf '\n== %s\n' "$*"; }
stop() { echo "refresh_preview: $*" >&2; exit 3; }

[ "$(git rev-parse --abbrev-ref HEAD)" = "$BRANCH" ] || stop "run this on $BRANCH (it is on $(git rev-parse --abbrev-ref HEAD))"
[ -z "$(git status --porcelain)" ] || stop "the worktree is not clean; commit or stash first"
for part in "${PARTS[@]}"; do
  git rev-parse --verify -q "p2/$part" >/dev/null || stop "no branch p2/$part"
done

OLD="$(git rev-parse HEAD)"
TOOL_FILES=(dev/tour/wave1.py dev/tour/wave1_web.mjs dev/tour/refresh_preview.sh)
STAMP="$(date -u +%Y%m%d-%H%M%S)"
git tag "preview-before-$STAMP" "$OLD"
if [ "$TOOLS" = 1 ]; then
  mkdir -p "${TMPDIR:-/tmp}/refresh-preview-$STAMP"
  SAVED="${TMPDIR:-/tmp}/refresh-preview-$STAMP"
  for f in "${TOOL_FILES[@]}"; do git show "$OLD:$f" > "$SAVED/$(basename "$f")"; done
fi

say "reset $BRANCH to main ($(git rev-parse --short main))"
git reset --hard main >/dev/null

# The one place that decides what "mechanical" means. Reads the conflicted file names from the file
# in $2; resolves what it may and exits 3 on the first conflict that is not mechanical.
SAVED_LIST="${TMPDIR:-/tmp}/refresh-preview-conflicts-$STAMP.txt"
resolve() {
  python3 - "$1" "$2" <<'PY'
import re
import subprocess
import sys

part = sys.argv[1]

REGEN = [
    re.compile(r"^uv\.lock$"),
    re.compile(r"^docs/reference/openapi\.json$"),
    re.compile(r"^packages/tl-schema/src/tl_schema/generated/"),
]
KEEP_BOTH = [
    re.compile(r"(^|/)pyproject\.toml$"),
    re.compile(r"^packages/tl-api/src/tl_api/(app|commands|errors|auth)\.py$"),
    re.compile(r"^packages/tl-mcp/src/tl_mcp/(server|identity)\.py$"),
    re.compile(r"^packages/tl-tui/src/tl_tui/(client|embedded)\.py$"),
    re.compile(r"(^|/)tests?/.*\.py$"),
]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def bail(path: str, why: str) -> None:
    print(f"NOT MECHANICAL: {path}: {why}", file=sys.stderr)
    sys.exit(3)


def integer_of(line: str) -> tuple[str, int] | None:
    m = re.search(r"\d+", line)
    if m is None or len(re.findall(r"\d+", line)) != 1:
        return None
    return re.sub(r"\d+", "#", line), int(m.group())


def base_count(path: str, shape: str) -> int | None:
    base = git("merge-base", "HEAD", f"p2/{part}").strip()
    try:
        text = git("show", f"{base}:{path}")
    except subprocess.CalledProcessError:
        return None
    for line in text.split("\n"):
        got = integer_of(line)
        if got is not None and got[0] == shape:
            return got[1]
    return None


def keep_both(path: str) -> None:
    text = open(path, encoding="utf-8").read()
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith("<<<<<<< "):
            out.append(lines[i])
            i += 1
            continue
        mid = next(j for j in range(i, len(lines)) if lines[j].startswith("======="))
        end = next(j for j in range(mid, len(lines)) if lines[j].startswith(">>>>>>> "))
        ours, theirs = lines[i + 1 : mid], lines[mid + 1 : end]
        if len(ours) == 1 and len(theirs) == 1:
            a, b = integer_of(ours[0]), integer_of(theirs[0])
            if a and b and a[0] == b[0] and a[1] != b[1]:  # a count that both sides moved
                base = base_count(path, a[0])
                if base is None:
                    bail(path, f"cannot find the base of {ours[0].strip()!r}")
                out.append(a[0].replace("#", str(a[1] + b[1] - base)))
                i = end + 1
                continue
        after = lines[end + 1] if end + 1 < len(lines) else ""
        if after.strip() == "..." and ours and ours[-1].strip().endswith('"""'):
            ours = [*ours, after]  # a method whose body `...` the shared tail gave to the last one
        out += ours
        if path.endswith(("client.py", "embedded.py")) and ours and ours[-1].strip():
            out.append("")
        out += theirs
        i = end + 1
    open(path, "w", encoding="utf-8").write("\n".join(out))


regen = False
for path in (line.strip() for line in open(sys.argv[2]) if line.strip()):
    if any(p.search(path) for p in REGEN):
        git("checkout", "--ours", "--", path)
        regen = True
    elif any(p.search(path) for p in KEEP_BOTH):
        keep_both(path)
        if re.search(r"^(<<<<<<<|=======$|>>>>>>>)", open(path, encoding="utf-8").read(), re.M):
            bail(path, "markers left after keeping both sides")
    else:
        bail(path, "a conflict in code or data that is not a list, a table or a generated file")
    git("add", "--", path)
print("regen" if regen else "")
PY
}

regenerate() {
  quiet uv lock >/dev/null
  quiet uv sync --all-packages >/dev/null
  quiet just gen >/dev/null
  quiet uv run python -m tl_api.openapi >/dev/null
}

for part in "${PARTS[@]}"; do
  say "merge p2/$part ($(git rev-parse --short "p2/$part"))"
  message="Merge p2/$part into $BRANCH"$'\n\n'"$TRAILER"
  if git merge --no-ff "p2/$part" -m "$message" >/dev/null 2>&1; then
    echo "clean"
    continue
  fi
  conflicts="$(git diff --name-only --diff-filter=U)"
  unmerged_kinds="$(git status --porcelain | grep -E '^(DU|UD|AU|UA|DD) ' || true)"
  [ -z "$unmerged_kinds" ] || { echo "$unmerged_kinds" >&2; stop "a delete or add-against-edit conflict in p2/$part; the merge is left open"; }
  [ -n "$conflicts" ] || stop "p2/$part failed to merge and no file is in conflict:$(git status --short | head -5)"
  echo "conflicts:"; echo "$conflicts" | sed 's/^/  /'
  printf '%s\n' "$conflicts" > "$SAVED_LIST"
  if ! resolve "$part" "$SAVED_LIST" >/dev/null; then
    stop "p2/$part has a conflict that is not mechanical; the merge is left open (git merge --abort to undo)"
  fi
  regenerate  # the merged code is conflict-free now: write the generated files again
  git add -A
  git commit -q -m "$message"
  echo "resolved: $(echo "$conflicts" | tr '\n' ' ')"
done

say "regenerate and put the tools back"
regenerate
if [ "$TOOLS" = 1 ]; then
  for f in "${TOOL_FILES[@]}"; do cp "$SAVED/$(basename "$f")" "$f"; done
  python3 - <<'PY'
import re
from pathlib import Path

path = Path("justfile")
text = path.read_text()
old = 'uv run python dev/tour/{{ if phase == "highlights" { "highlights" } else { "phase" + phase } }}.py'
new = 'uv run python dev/tour/{{ if phase == "highlights" { "highlights" } else if phase == "wave1" { "wave1" } else { "phase" + phase } }}.py'
if '"wave1"' not in text:
    if old not in text:
        raise SystemExit("NOT MECHANICAL: justfile: the tour recipe has changed; add `wave1` by hand")
    text = text.replace(old, new)
    text = re.sub(
        r"(# Regenerate the screenshot tour[^\n]*\n)",
        r"\1# (`just tour wave1`: the web client, awp and materials preview, docs/reports/tour/wave1)\n",
        text,
        count=1,
    )
    path.write_text(text)
PY
fi
if [ -n "$(git status --porcelain)" ]; then
  git add -A
  git commit -q -m "P2-W1-PREVIEW: regenerate after the merges and restore the preview tools

$TRAILER"
fi

if [ "$CHECK" = 1 ]; then
  say "just check"
  NODE_OPTIONS=--max-old-space-size=6144 just check >"${TMPDIR:-/tmp}/refresh-preview-check-$STAMP.log" 2>&1 \
    || { tail -30 "${TMPDIR:-/tmp}/refresh-preview-check-$STAMP.log" >&2; stop "just check failed (log: ${TMPDIR:-/tmp}/refresh-preview-check-$STAMP.log)"; }
  echo "just check clean"
fi

say "done: $BRANCH is at $(git rev-parse --short HEAD) (old head tagged preview-before-$STAMP)"
git log --oneline --first-parent -6 | cat

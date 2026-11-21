#!/usr/bin/env bash
# Run the whole skill on the FZK-Haus sample of the xray-ref repo (models/AC20-FZK-Haus.ifc, web/public/samples/fzk-haus.*).
#   PYTHON=/path/to/python-with-ifcopenshell bash selftest.sh [workdir]
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; repo="$(cd "$here/../../.." && pwd)"; py="${PYTHON:-python3}"; w="${1:-$(mktemp -d)}"
x="$repo/web/public/samples/fzk-haus.xer"; c="$repo/web/public/samples/fzk-haus.4d.json"; m="$repo/models/AC20-FZK-Haus.ifc"
python3 "$here/xer_read.py" "$x" -o "$w/schedule.json" >/dev/null
"$py" "$here/ifc_read.py" "$m" -o "$w/model.json" >/dev/null
python3 "$here/link.py" --xer "$w/schedule.json" --ifc "$w/model.json" --config "$c" --min-coverage 1 -o "$w/links.json" >/dev/null
"$py" "$here/apply_links.py" --ifc "$m" --links "$w/links.json" --xer "$x" -o "$w/model.4d.ifc" >/dev/null
"$py" "$here/verify.py" --ifc "$w/model.4d.ifc" --links "$w/links.json" >/dev/null
python3 "$here/xer_write.py" --xer "$x" --links "$w/links.json" -o "$w/schedule.4d.xer" >/dev/null
python3 "$here/anim_write.py" --links "$w/links.json" --ifc "$w/model.json" --length 30 -o "$w/build.xrayanim" >/dev/null
node "$here/xrayanim_check.mjs" "$w/build.xrayanim" >/dev/null
echo "ok: $w"

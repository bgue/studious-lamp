#!/usr/bin/env bash
# Regenerate the SQL tables and the JSON Schema from xray_4d.yaml, and validate the examples.
# Needs LinkML (tested with linkml 1.11.1 + linkml-runtime 1.11.1):  python3 -m venv .venv && .venv/bin/pip install linkml==1.11.1 linkml-runtime==1.11.1
set -euo pipefail
cd "$(dirname "$0")"
BIN="${LINKML_BIN:-.venv/bin}"
"$BIN/gen-sqltables" xray_4d.yaml > xray_4d.sql
"$BIN/gen-json-schema" xray_4d.yaml > xray_4d.schema.json
for f in examples/*.yaml; do "$BIN/linkml-validate" -s xray_4d.yaml -C LinkDataset "$f"; done
echo "ok: xray_4d.sql, xray_4d.schema.json, examples valid"

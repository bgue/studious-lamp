#!/usr/bin/env bash
# Fetch the pinned Litestream release once into dev/data/tools/ (git-ignored), per the ADR-0002
# download rule: one attempt, no retry loop. Exit 0 when the binary is ready, 1 otherwise.
#
# Litestream v0.3.13, Apache-2.0, https://github.com/benbjohnson/litestream/releases/tag/v0.3.13
set -euo pipefail
cd "$(dirname "$0")/../.."
VERSION=v0.3.13
SHA256=eb75a3de5cab03875cdae9f5f539e6aedadd66607003d9b1e7a9077948818ba0
DIR=dev/data/tools
if [ -x "$DIR/litestream" ] && "$DIR/litestream" version | grep -q "$VERSION"; then
  exit 0
fi
[ "$(uname -m)" = x86_64 ] || { echo "only linux/amd64 is pinned" >&2; exit 1; }
mkdir -p "$DIR"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
curl -fsSL -m 120 -o "$TMP/ls.tgz" \
  "https://github.com/benbjohnson/litestream/releases/download/$VERSION/litestream-$VERSION-linux-amd64.tar.gz" \
  || { echo "could not download Litestream $VERSION" >&2; exit 1; }
echo "$SHA256  $TMP/ls.tgz" | sha256sum -c - >/dev/null || { echo "checksum mismatch" >&2; exit 1; }
tar -xzf "$TMP/ls.tgz" -C "$DIR" litestream
echo "Litestream $VERSION is in $DIR/litestream" >&2

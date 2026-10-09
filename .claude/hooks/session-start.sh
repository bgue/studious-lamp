#!/bin/bash
# SessionStart hook for Throughline cloud sessions.
# Installs the toolchain from docs/adr/0002-build-environment-constraints.md:
#   just (via uv), native PostgreSQL 16 with db tl_test, and the uv workspace once it exists.
# Idempotent: every step checks before acting, so warm starts finish in a few seconds.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

log() { echo "[session-start] $*" >&2; }
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
export PATH="$HOME/.local/bin:$PATH"

# Persist env for the session (deduplicated).
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  add_env() { grep -qxF "$1" "$CLAUDE_ENV_FILE" 2>/dev/null || echo "$1" >> "$CLAUDE_ENV_FILE"; }
  add_env 'export PATH="$HOME/.local/bin:$PATH"'
  add_env 'export TL_PG_URL="postgresql://postgres:postgres@localhost:5432/tl_test"'
fi

# 1. just
if ! command -v just >/dev/null 2>&1; then
  log "installing just"
  uv tool install rust-just >/dev/null 2>&1 || log "WARN: just install failed"
fi

# 2. PostgreSQL 16 (native; no Docker daemon in this container)
SUDO=""
if [ "$(id -u)" != "0" ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi
as_postgres() {
  # Run psql as the postgres OS user whether or not we are root; cd /tmp avoids chdir warnings.
  if command -v sudo >/dev/null 2>&1; then (cd /tmp && sudo -u postgres "$@"); else (cd /tmp && su postgres -c "$(printf '%q ' "$@")"); fi
}
if [ ! -x /usr/lib/postgresql/16/bin/pg_ctl ]; then
  log "installing postgresql"
  $SUDO apt-get update -qq >/dev/null 2>&1 || true
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq postgresql postgresql-contrib >/dev/null 2>&1 \
    || log "WARN: postgresql install failed; parity tests will skip"
fi
if [ -x /usr/lib/postgresql/16/bin/pg_ctl ]; then
  if ! pg_isready -q -h localhost -p 5432 2>/dev/null; then
    log "starting postgresql"
    $SUDO pg_ctlcluster 16 main start >/dev/null 2>&1 || log "WARN: postgresql start failed"
    for _ in 1 2 3 4 5 6 7 8 9 10; do pg_isready -q -h localhost -p 5432 2>/dev/null && break; sleep 1; done
  fi
  if pg_isready -q -h localhost -p 5432 2>/dev/null; then
    as_postgres psql -qtAc "ALTER USER postgres PASSWORD 'postgres';" >/dev/null 2>&1 || true
    if [ "$(as_postgres psql -qtAc "SELECT 1 FROM pg_database WHERE datname='tl_test'" 2>/dev/null)" != "1" ]; then
      log "creating database tl_test"
      as_postgres psql -qc "CREATE DATABASE tl_test;" >/dev/null 2>&1 || true
    fi
  fi
fi

# 3. Python workspace (exists from Phase 0 increment 1 onward)
if [ -f "$PROJECT_DIR/pyproject.toml" ]; then
  log "uv sync"
  (cd "$PROJECT_DIR" && uv sync --all-packages >/dev/null 2>&1) || (cd "$PROJECT_DIR" && uv sync >/dev/null 2>&1) \
    || log "WARN: uv sync failed"
fi

# 4. Git identity for agent commits
git config --global user.name >/dev/null 2>&1 || git config --global user.name "Claude"
git config --global user.email >/dev/null 2>&1 || git config --global user.email "noreply@anthropic.com"

log "done"

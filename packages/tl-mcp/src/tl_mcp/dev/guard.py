"""The dev-data guard (FANOUT D12; brief 25.3: local and CI only, never production data).

Every dev tool asks this module before it touches a database, a file, a process or a socket:

* :func:`resolve_target` accepts a SQLite file only under the repository's ``dev/`` directory or a
  temporary directory, and a Postgres URL only when the host is this machine and the database name
  starts with ``tl_test`` or ``tl_dev``;
* :func:`check_environment` refuses to start when ``TL_ENV`` names a real environment;
* :func:`select_pytest_args` turns a marker, a keyword and test paths from fixed allow-lists into
  the argument list of one pytest run (no shell, no free-form options);
* :func:`check_loopback_url` accepts a webhook target only when it is this machine, and resolves
  it without DNS;
* :func:`safe_child` finds a document under a directory by a plain file name.

The SQL guard for ``query_db`` is in :mod:`tl_mcp.dev.sqlguard`. Every check fails closed: anything
not recognised is refused.
"""

from __future__ import annotations

import ipaddress
import os
import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from tl_mcp.dev.errors import DevGuardError

ALLOWED_ENVS = frozenset({"", "dev", "test", "ci"})
"""``TL_ENV`` values the dev server runs under. Unset counts as dev."""

PG_DATABASE_PREFIXES = ("tl_test", "tl_dev")
PG_LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1"})
_PG_OPTIONS = re.compile(r"^-csearch_path=[a-z_][a-z0-9_]{0,62}$")
"""The one query parameter a target may carry: the schema ``admin.schema_url`` writes."""

DEFAULT_DB = "dev/data/tl.db"


# --- the repository ------------------------------------------------------------------------------


def find_repo_root(start: Path | None = None) -> Path:
    """The repository root: the nearest parent holding ``AGENTS.md``, ``justfile`` and ``dev/``."""
    here = (start if start is not None else Path(__file__)).resolve()
    for parent in (here, *here.parents):
        if (parent / "AGENTS.md").is_file() and (parent / "justfile").is_file():
            if (parent / "dev").is_dir():
                return parent
    raise DevGuardError("cannot find the repository root; run the dev server from a checkout")


def check_environment(env: dict[str, str] | None = None) -> None:
    """Refuse to run when ``TL_ENV`` is anything but dev, test, ci or unset."""
    value = (env if env is not None else dict(os.environ)).get("TL_ENV", "").strip().lower()
    if value not in ALLOWED_ENVS:
        raise DevGuardError(
            f"TL_ENV={value!r}: the dev MCP server only runs with TL_ENV unset, dev, test or ci"
        )


# --- the database --------------------------------------------------------------------------------


@dataclass(frozen=True)
class DevTarget:
    """A database the dev tools may use: a SQLite file or a local ``tl_test*``/``tl_dev*`` Postgres.

    ``path`` is the resolved file for SQLite; ``url`` is the full URL for Postgres and is never
    printed (use :attr:`display`).
    """

    kind: Literal["sqlite", "postgres"]
    path: Path | None = None
    url: str | None = None

    @property
    def dialect(self) -> str:
        return self.kind

    @property
    def display(self) -> str:
        """Text that is safe to show an agent: the file's repository-relative name, or the URL
        without its password."""
        if self.kind == "sqlite":
            assert self.path is not None
            return self.path.name
        assert self.url is not None
        return make_url(self.url).render_as_string(hide_password=True)

    @property
    def db_arg(self) -> str | Path:
        """What ``tl_adapters.db`` functions take as a database target."""
        if self.kind == "sqlite":
            assert self.path is not None
            return self.path
        assert self.url is not None
        return self.url


def temp_roots() -> tuple[Path, ...]:
    """Temporary directories a SQLite file may live in (resolved, so a symlink cannot leave)."""
    roots = {Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve()}
    return tuple(sorted(roots))


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def resolve_sqlite(raw: str, *, repo_root: Path, extra_roots: Sequence[Path] = ()) -> DevTarget:
    if "\x00" in raw or "://" in raw or raw.startswith("file:"):
        raise DevGuardError("a SQLite target is a plain file path")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    resolved = candidate.resolve()  # follows symlinks, collapses `..`
    roots = (repo_root.resolve() / "dev", *temp_roots(), *(r.resolve() for r in extra_roots))
    if not any(_inside(resolved, root) for root in roots):
        raise DevGuardError(
            "refused: a SQLite file must be under the repository's dev/ directory or a temporary "
            "directory"
        )
    if resolved.is_dir():
        raise DevGuardError("the database target is a directory")
    return DevTarget("sqlite", path=resolved)


def resolve_postgres(raw: str) -> DevTarget:
    try:
        url = make_url(raw)
    except ArgumentError as exc:
        raise DevGuardError("the Postgres URL does not parse") from exc
    if url.drivername not in ("postgresql", "postgres"):
        raise DevGuardError("a Postgres target is a postgresql:// URL")
    host = (url.host or "").lower()
    if host not in PG_LOCAL_HOSTS:
        raise DevGuardError("refused: the dev server only uses a Postgres on this machine")
    database = url.database or ""
    if not database.startswith(PG_DATABASE_PREFIXES):
        raise DevGuardError(
            "refused: the database name must start with tl_test or tl_dev "
            f"(got {database!r}); the dev server never touches other databases"
        )
    for key, value in url.query.items():
        if key != "options" or not isinstance(value, str) or not _PG_OPTIONS.fullmatch(value):
            raise DevGuardError(
                "refused: the only URL parameter allowed is options=-csearch_path=<schema>"
            )
    return DevTarget("postgres", url=raw)


def resolve_target(
    raw: str | Path, *, repo_root: Path, extra_roots: Sequence[Path] = ()
) -> DevTarget:
    """The dev database ``raw`` names, or :class:`DevGuardError`.

    ``raw`` is a SQLite file path (relative paths are relative to the repository root) or a
    ``postgresql://`` URL. ``extra_roots`` is for tests only.
    """
    text = str(raw)
    if text.startswith(("postgresql://", "postgres://", "postgresql+")):
        return resolve_postgres(text)
    return resolve_sqlite(text, repo_root=repo_root, extra_roots=extra_roots)


# --- tests ---------------------------------------------------------------------------------------

ALLOWED_MARKERS = frozenset({"parity", "requires_postgres"})
ALLOWED_ADAPTERS = frozenset({"sqlite", "postgres", "sqlite,postgres"})
_TEST_PATH = re.compile(
    r"^(?:packages/[a-z][a-z0-9-]*/tests|tests)(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*)*"
    r"(?:::[A-Za-z_][A-Za-z0-9_]*){0,2}$"
)
_KEYWORD = re.compile(r"^[A-Za-z0-9_() ]{1,200}$")
MAX_TEST_PATHS = 20


def select_pytest_args(
    *,
    repo_root: Path,
    paths: Sequence[str] = (),
    marker: str | None = None,
    keyword: str | None = None,
    adapters: str | None = None,
) -> list[str]:
    """The arguments that follow ``python -m pytest`` for one filtered run, or a refusal.

    Only these filters exist, each checked against an allow-list:

    * ``marker``: ``parity`` or ``requires_postgres``;
    * ``keyword``: letters, digits, ``_``, spaces and parentheses (pytest's ``-k`` expression
      language is a parser, not ``eval``, and has no way to name a file or an option);
    * ``paths``: test files or directories under ``packages/<pkg>/tests`` or ``tests``, optionally
      with ``::TestClass::test_name``; each must exist inside the repository;
    * ``adapters``: ``sqlite``, ``postgres`` or ``sqlite,postgres``.

    Nothing else reaches pytest: no option, no plugin, no ``conftest`` path, no shell.
    """
    args: list[str] = ["-q", "-p", "no:cacheprovider"]
    if marker is not None:
        if marker not in ALLOWED_MARKERS:
            raise DevGuardError(f"marker must be one of {', '.join(sorted(ALLOWED_MARKERS))}")
        args += ["-m", marker]
    if keyword is not None:
        if not _KEYWORD.fullmatch(keyword):
            raise DevGuardError("keyword may only hold letters, digits, _, spaces and parentheses")
        args += ["-k", keyword]
    if adapters is not None:
        if adapters not in ALLOWED_ADAPTERS:
            raise DevGuardError("adapters must be sqlite, postgres or sqlite,postgres")
        args += ["--adapters", adapters]
    if len(paths) > MAX_TEST_PATHS:
        raise DevGuardError(f"at most {MAX_TEST_PATHS} test paths")
    root = repo_root.resolve()
    for raw in paths:
        if not _TEST_PATH.fullmatch(raw):
            raise DevGuardError(
                "a test path is relative, under packages/<package>/tests or tests, and may end "
                "in ::test_name"
            )
        file_part = raw.split("::", 1)[0]
        target = (root / file_part).resolve()
        if not _inside(target, root) or not target.exists():
            raise DevGuardError(f"no such test path: {file_part}")
        if target.is_file() and target.suffix != ".py":
            raise DevGuardError("a test file ends in .py")
        args.append(raw)
    return args


# --- webhooks ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LoopbackUrl:
    """A webhook target that is this machine, resolved without DNS."""

    scheme: str
    ip: str
    port: int
    path_and_query: str

    @property
    def host_header(self) -> str:
        host = f"[{self.ip}]" if ":" in self.ip else self.ip
        default = 443 if self.scheme == "https" else 80
        return host if self.port == default else f"{host}:{self.port}"


_USERINFO = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*://)[^/?#@]*@")


def redact_url(url: str) -> str:
    """``url`` with any ``user:password@`` part replaced by ``***@``, for audit lines and errors."""
    return _USERINFO.sub(r"\1***@", url)


def check_loopback_url(url: str) -> LoopbackUrl:
    """``url`` as a loopback target, or :class:`DevGuardError`.

    The host must be ``localhost`` or a literal loopback address (``127.0.0.0/8``, ``::1``). No
    other spelling is accepted (no decimal, octal or hex IPv4, no DNS name), no credentials, no
    fragment. ``localhost`` is taken to be 127.0.0.1 without asking the resolver.
    """
    if len(url) > 2048 or any(ord(c) < 0x21 or ord(c) > 0x7E for c in url):
        raise DevGuardError("the target URL must be plain ASCII without spaces")
    try:
        parts = urlsplit(url)
        port = parts.port
        host = parts.hostname or ""
    except ValueError as exc:
        raise DevGuardError("the target URL does not parse") from exc
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise DevGuardError("the target must be an http(s) URL")
    if parts.username is not None or parts.password is not None or parts.fragment:
        raise DevGuardError("the target URL must not carry credentials or a fragment")
    if host.lower() == "localhost":
        ip = "127.0.0.1"
    else:
        try:
            address = ipaddress.ip_address(host.split("%", 1)[0])
        except ValueError as exc:
            raise DevGuardError(
                "refused: the target must be localhost or a literal loopback address"
            ) from exc
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        if not address.is_loopback:
            raise DevGuardError("refused: send_test_webhook only targets loopback receivers")
        ip = str(address)
    path = parts.path or "/"
    return LoopbackUrl(
        scheme=scheme,
        ip=ip,
        port=port or (443 if scheme == "https" else 80),
        path_and_query=path + (f"?{parts.query}" if parts.query else ""),
    )


# --- documents -----------------------------------------------------------------------------------

_DOC_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def safe_child(directory: Path, name: str, suffixes: Sequence[str]) -> Path:
    """The file ``name`` directly inside ``directory``, or :class:`DevGuardError`.

    ``name`` is a plain file name: no separator, no ``..``, one of ``suffixes``. The resolved path
    must still be inside ``directory`` (a symlink that leaves it is refused).
    """
    if not _DOC_NAME.fullmatch(name) or ".." in name or not name.endswith(tuple(suffixes)):
        raise DevGuardError(f"not a document name: {name[:60]!r}")
    root = directory.resolve()
    target = (root / name).resolve()
    if target.parent != root or not target.is_file():
        raise DevGuardError(f"no such document: {name}")
    return target


def list_documents(directory: Path, suffixes: Sequence[str]) -> list[str]:
    """Names of the regular files directly inside ``directory`` that ``safe_child`` would open."""
    if not directory.is_dir():
        return []
    names: list[str] = []
    for entry in sorted(directory.iterdir()):
        try:
            safe_child(directory, entry.name, suffixes)
        except DevGuardError:
            continue
        names.append(entry.name)
    return names

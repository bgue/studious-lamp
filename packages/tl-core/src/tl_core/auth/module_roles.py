"""Module roles: the role table, the holder, and the one resolver (ADR-0021; roles-mvp.md 2 and 4).

Three roles (``viewer``, ``user``, ``superuser``) are granted per project and module as ledgered
``Account.ModuleRole*`` events (``module_grants``). Which role holds which access *word* is data:
``schema/settings/module-roles.yaml``, loaded by :func:`load_role_table`. Every question "what does
this holder hold here" is answered by :func:`effective_roles`; nothing else reads the grants.

Precedence for ``effective_roles`` (the first step that applies wins):

1. a disabled, missing or inexact account (actor is not exactly ``actor_for(kind, name)``): none;
2. an active human ``admin``: every role and word, plus ``admin``;
3. scope ``company``: explicit ``company`` grants for the module when it declares ``company_roles``,
   else derived only; a ``project:<id>`` scope never reads a ``company`` grant (and the reverse);
4. explicit grants for ``(account, project, module)``: they *replace* the derived roles;
5. explicit grants for ``(account, project, "*")``;
6. roles derived from the account's roles through the table's ``derive`` block;
7. otherwise none.

An agent holds at most ``agent_roles``. A ``svc:`` actor keeps its declared access (``held_access``,
ADR-0017 section 7). Module roles never filter reads and give no clearance (ADR-0016 is unchanged).
A module may declare a fine access word (``awp.cwp.release``, W0-B1). :func:`command_index` reads
it as its table word, once, so every other reader sees a table word or a platform word only.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

import yaml
from sqlalchemy import Connection, text

from tl_core.auth.access_words import TABLE_WORDS, table_word
from tl_core.auth.errors import ForbiddenError, RoleTableError
from tl_core.auth.names import actor_for, is_id
from tl_core.auth.queries import find_account
from tl_core.auth.types import ROLES, AccountKind, Principal
from tl_core.modules import ModuleLoadError, load_modules
from tl_core.services.commands import Command

if TYPE_CHECKING:
    from tl_core.actions import Holds, Level

_REPO_ROOT = Path(__file__).resolve().parents[5]
#: The role table the platform ships. There is no override: the table is code-reviewed.
DEFAULT_ROLE_TABLE_FILE = _REPO_ROOT / "schema" / "settings" / "module-roles.yaml"

#: Platform words: not in the table and never grantable.
PLATFORM_WORDS = frozenset({"admin", "company"})
ALL_MODULES = "*"
COMPANY = "company"

_NAME = re.compile(r"[a-z][a-z0-9_]{0,31}")
_MODULE_NAME = re.compile(r"[a-z][a-z0-9_]{0,62}")
_TOP_KEYS = frozenset({"version", "words", "roles", "agent_roles", "derive"})

Source = Literal["admin", "granted", "granted_all_modules", "derived", "service", "none"]


# --- the role table --------------------------------------------------------------------------


@dataclass(frozen=True)
class RoleTable:
    """``schema/settings/module-roles.yaml`` after validation. Immutable; roles keep file order."""

    words: Mapping[str, str]  # grantable word -> description
    roles: Mapping[str, tuple[str, ...]]  # role -> the words it holds (display order)
    agent_roles: tuple[str, ...]
    derive: Mapping[
        str, tuple[tuple[str, str], ...]
    ]  # account role -> ((module or "*", role), ...)

    def words_of(self, roles: frozenset[str]) -> frozenset[str]:
        found: set[str] = set()
        for role in roles:
            found.update(self.roles.get(role, ()))
        return frozenset(found)


def _fail(what: str) -> RoleTableError:
    return RoleTableError(f"module role table: {what}")


def _mapping(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(
        isinstance(k, str) for k in cast("dict[Any, Any]", value)
    ):
        raise _fail(f"{what} must be a mapping")
    return cast("dict[str, Any]", value)


def _name_list(value: Any, what: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in cast("list[Any]", value)):
        raise _fail(f"{what} must be a list of names")
    return cast("list[str]", value)


def parse_role_table(data: Any) -> RoleTable:
    """Validate parsed YAML. Any unknown word, role, account role or key is a ``RoleTableError``."""
    top = _mapping(data, "the file")
    extra = sorted(set(top) - _TOP_KEYS)
    if extra:
        raise _fail(f"unknown key {', '.join(extra)}")
    if top.get("version") != 1:
        raise _fail("version must be 1")
    words = _mapping(top.get("words"), "words")
    for word, description in words.items():
        if _NAME.fullmatch(word) is None or word in PLATFORM_WORDS:
            raise _fail(f"{word!r} cannot be a grantable word")
        if not isinstance(description, str):
            raise _fail(f"word {word} needs a description")
    raw_roles = _mapping(top.get("roles"), "roles")
    if not raw_roles:
        raise _fail("roles is empty")
    roles: dict[str, tuple[str, ...]] = {}
    for role, held in raw_roles.items():
        if _NAME.fullmatch(role) is None:
            raise _fail(f"{role!r} is not a role name")
        listed = _name_list(held, f"role {role}")
        unknown = sorted(set(listed) - set(words))
        if unknown:
            raise _fail(f"role {role} holds unknown word {', '.join(unknown)}")
        roles[role] = tuple(listed)
    agent_roles = _name_list(top.get("agent_roles"), "agent_roles")
    unknown = sorted(set(agent_roles) - set(roles))
    if unknown:
        raise _fail(f"agent_roles names unknown role {', '.join(unknown)}")
    derive: dict[str, tuple[tuple[str, str], ...]] = {}
    for account_role, entries in _mapping(top.get("derive"), "derive").items():
        if account_role not in ROLES:
            raise _fail(f"derive names unknown account role {account_role!r}")
        if not isinstance(entries, list):
            raise _fail(f"derive.{account_role} must be a list")
        pairs: list[tuple[str, str]] = []
        for entry in cast("list[Any]", entries):
            item = _mapping(entry, f"a derive.{account_role} entry")
            module, role = item.get("module"), item.get("role")
            if set(item) != {"module", "role"} or not isinstance(module, str):
                raise _fail(f"a derive.{account_role} entry needs exactly module and role")
            if module != ALL_MODULES and _MODULE_NAME.fullmatch(module) is None:
                raise _fail(f"derive.{account_role} names an unusable module {module!r}")
            if not isinstance(role, str) or role not in roles:
                raise _fail(f"derive.{account_role} names unknown role {role!r}")
            pairs.append((module, role))
        derive[account_role] = tuple(pairs)
    return RoleTable(
        words={w: str(d) for w, d in words.items()},
        roles=roles,
        agent_roles=tuple(agent_roles),
        derive=derive,
    )


_table_lock = threading.Lock()
_default_table: RoleTable | None = None


def load_role_table(path: Path | str | None = None) -> RoleTable:
    """The platform's role table, read once per process; a ``path`` reads that file, uncached."""
    global _default_table
    if path is not None:
        return _read(Path(path))
    with _table_lock:
        if _default_table is None:
            _default_table = _read(DEFAULT_ROLE_TABLE_FILE)
        return _default_table


def _read(path: Path) -> RoleTable:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise _fail(f"{path.name} cannot be read: {type(exc).__name__}") from exc
    return parse_role_table(data)


# --- the holder ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Holder:
    """Who is asking. Never read from a request body."""

    actor: str
    kind: AccountKind | Literal["service"]
    account_id: str | None
    account_roles: tuple[str, ...]


def holder_for_principal(p: Principal) -> Holder:
    """The API's holder. A dev-token principal has no account row (its id starts ``dev:``)."""
    return Holder(actor=p.actor, kind=p.kind, account_id=p.account_id, account_roles=tuple(p.roles))


def holder_for_actor(conn: Connection, actor: str) -> Holder:
    """CLI, embedded and runner: the holder for an exact actor string, from ``cur_account``.

    An actor that names no account gets a holder with no ``account_id`` (it resolves to none); a
    normalised twin of a real name keeps the account's id, so precedence 1 refuses it as inexact.
    """
    if actor.startswith("svc:"):
        return Holder(actor=actor, kind="service", account_id=None, account_roles=())
    prefix, _, name = actor.partition(":")
    kind: AccountKind = "agent" if prefix == "agent" else "person"
    if prefix not in ("user", "agent") or not name:
        return Holder(actor=actor, kind=kind, account_id=None, account_roles=())
    try:
        account = find_account(conn, username=name)
    except Exception:  # an unusable name is no account
        account = None
    if account is None:
        return Holder(actor=actor, kind=kind, account_id=None, account_roles=())
    return Holder(
        actor=actor,
        kind=account.kind,
        account_id=account.account_id,
        account_roles=tuple(account.roles),
    )


# --- the resolver ----------------------------------------------------------------------------


@dataclass(frozen=True)
class EffectiveRoles:
    roles: frozenset[str]
    words: frozenset[str]
    source: Source


_NONE = EffectiveRoles(frozenset(), frozenset(), "none")


def _account_is_live(conn: Connection, holder: Holder) -> bool:
    """Precedence 1: the holder is an active account and its actor is exactly the account's."""
    account_id = holder.account_id
    if account_id is None or not is_id(account_id):
        return False
    if account_id.startswith("dev:"):  # a dev-token principal: no row, trusted as authenticated
        return holder.actor == account_id[4:]
    row = (
        conn.execute(
            text("SELECT username, kind, status FROM cur_account WHERE account_id = :a"),
            {"a": account_id},
        )
        .mappings()
        .first()
    )
    if row is None or row["status"] != "active" or row["kind"] != holder.kind:
        return False
    return holder.actor == actor_for(cast(AccountKind, row["kind"]), str(row["username"]))


def _grants(conn: Connection, account_id: str, project: str, module: str) -> frozenset[str]:
    found = conn.execute(
        text(
            "SELECT role FROM cur_account_module_role "
            "WHERE account_id = :a AND project = :p AND module = :m"
        ),
        {"a": account_id, "p": project, "m": module},
    ).all()
    return frozenset(str(r[0]) for r in found)


def _derived(table: RoleTable, holder: Holder, module: str) -> frozenset[str]:
    found: set[str] = set()
    for account_role in holder.account_roles:
        for target, role in table.derive.get(account_role, ()):
            if target in (ALL_MODULES, module):
                found.add(role)
    return frozenset(found)


def _service(conn: Connection, holder: Holder) -> EffectiveRoles:
    from tl_core.integration.actor_access import held_access  # avoid an import cycle

    held = held_access(conn, holder.actor)
    if held == "user":
        return EffectiveRoles(frozenset(), frozenset({"user"}), "service")
    if held == "controller":
        return EffectiveRoles(frozenset(), frozenset({"user", "controller"}), "service")
    return _NONE  # nothing, or admin (a service actor is never an admin)


def _declares_company_roles(module: str) -> bool:
    return any(spec.name == module and spec.company_roles for spec in load_modules())


def effective_roles(conn: Connection, holder: Holder, *, scope: str, module: str) -> EffectiveRoles:
    """What ``holder`` holds for ``module`` at ``scope`` (``company`` or ``project:<id>``)."""
    if holder.kind == "service":
        return _service(conn, holder)
    if not _account_is_live(conn, holder):  # 1
        return _NONE
    table = load_role_table()
    assert holder.account_id is not None  # _account_is_live
    if holder.kind == "person" and "admin" in holder.account_roles:  # 2
        return EffectiveRoles(
            frozenset(table.roles),
            frozenset(table.words) | {"admin"},
            "admin",
        )
    source: Source = "derived"
    roles: frozenset[str] = frozenset()
    if scope == COMPANY:  # 3: explicit grants only where the module declares company roles
        if _declares_company_roles(module):
            roles = _grants(conn, holder.account_id, COMPANY, module)
            source = "granted"
    else:
        roles = _grants(conn, holder.account_id, scope, module)  # 4
        source = "granted"
        if not roles:
            roles = _grants(conn, holder.account_id, scope, ALL_MODULES)  # 5
            source = "granted_all_modules"
    roles &= frozenset(table.roles)  # a role no longer in the table grants nothing
    if not roles:
        roles = _derived(table, holder, module)  # 6
        source = "derived"
    if holder.kind == "agent":
        roles &= frozenset(table.agent_roles)
    if not roles:  # 7
        return _NONE
    return EffectiveRoles(roles, table.words_of(roles), source)


def holds_word(conn: Connection, holder: Holder, *, scope: str, module: str, word: str) -> bool:
    return word in effective_roles(conn, holder, scope=scope, module=module).words


def scoped_holds(
    conn: Connection, holder: Holder, *, scope: str, module: str, base: Holds
) -> Holds:
    """A ``Holds`` for an ``actions`` hook: ``admin`` from ``base``, the rest from the roles."""
    words = effective_roles(conn, holder, scope=scope, module=module).words

    def holds(level: Level) -> bool:
        if level == "admin":
            return base("admin")
        return level in words

    return holds


def normalise_word(word: str) -> str:
    """The word the resolver understands for a declared access ``word``.

    ``admin`` and ``company`` (platform words) and the table words pass unchanged; any other word
    is a fine word and becomes its table word. An unknown word raises ``AccessWordError`` (fail
    closed: a typo is a start-up failure, never an open door). This is the one place a fine word
    is read.
    """
    if word in PLATFORM_WORDS or word in TABLE_WORDS:
        return word
    return table_word(word)


def command_index() -> Mapping[str, tuple[str, str]]:
    """Command class name -> ``(module, word)``, from ``ModuleSpec.command_words``.

    The word is normalised (:func:`normalise_word`): a table word or a platform word, never a
    fine one.
    """
    index: dict[str, tuple[str, str]] = {}
    for spec in load_modules():
        for name, word in spec.command_words.items():
            if name in index:
                raise ModuleLoadError(
                    f"command {name!r} is declared by modules {index[name][0]!r} and {spec.name!r}"
                )
            index[name] = (spec.name, normalise_word(word))
    return index


def require_word(
    conn: Connection, holder: Holder, *, scope: str, module: str, word: str, what: str
) -> None:
    """Refuse (``ForbiddenError``) a holder that lacks ``word`` for ``module`` at ``scope``."""
    if not holds_word(conn, holder, scope=scope, module=module, word=word):
        raise ForbiddenError(f"{what} needs the {word} access word for {module} on {scope}")


def require_command_access(
    conn: Connection, command: Command, *, holder: Holder | None = None
) -> None:
    """Refuse (``ForbiddenError``) a module command whose holder lacks the command's word here.

    A command no module declares is unchanged. ``holder`` defaults to the command's own actor,
    resolved from ``cur_account``; the API passes the principal's holder.
    """
    name = type(command).__name__
    found = command_index().get(name)
    if found is None:
        return
    module, word = found
    if word == "company":  # admin at company scope, else the plain user word
        word = "admin" if command.scope == COMPANY else "user"
    who = holder if holder is not None else holder_for_actor(conn, command.actor)
    require_word(conn, who, scope=command.scope, module=module, word=word, what=name)

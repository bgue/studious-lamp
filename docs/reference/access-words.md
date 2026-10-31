# Access words

Purpose: list the fine access words of the modules, the table word each one needs, and how a module author uses them.

The single source is [`schema/settings/access-words.yaml`](../../schema/settings/access-words.yaml). This page copies it for reading; if the two differ, the yaml wins.

## The three table words

The role table is [`schema/settings/module-roles.yaml`](../../schema/settings/module-roles.yaml). It grants three table words:

- `read` (role `viewer`): read the module's records.
- `user` (role `user`): create and work records.
- `controller` (role `superuser`): approve, sign off, issue, configure, void.

A module role does not filter reads: a `superuser` grant gives no restricted read (ADR-0016 is unchanged).

## Fine words

| word | needs | module |
|---|---|---|
| `awp.view` | `read` | awp |
| `awp.wbs.configure` | `controller` | awp |
| `awp.path.configure` | `controller` | awp |
| `awp.cwa.edit` | `user` | awp |
| `awp.cwp.edit` | `user` | awp |
| `awp.cwp.release` | `controller` | awp |
| `awp.cwp.close` | `controller` | awp |
| `awp.void` | `controller` | awp |
| `awp.package.edit` | `user` | awp |
| `materials.view` | `read` | materials |
| `materials.library.edit` | `controller` | materials |
| `materials.item.adopt` | `user` | materials |
| `materials.location.configure` | `controller` | materials |
| `materials.po.edit` | `user` | materials |
| `materials.receive` | `user` | materials |
| `materials.receipt.decide` | `user` | materials |
| `materials.void` | `controller` | materials |
| `materials.move` | `user` | materials |
| `materials.reserve` | `user` | materials |
| `materials.adjust` | `controller` | materials |
| `materials.mto.publish` | `controller` | materials |
| `materials.mto.assign` | `user` | materials |

## How a module author uses a fine word

1. Give each command in `ModuleSpec.command_words` a word: a table word (`read`, `user` or `controller`) or a fine word from the table above.
2. A fine word needs one row in `access-words.yaml` that names one table word.
3. Editing that file is a `schema/**` change. Only a schema ticket that names a human approver may make it (`AGENTS.md`).
4. The API reads the fine word once, in `command_index()` (`tl_core.auth.module_roles`).
5. An unknown table word, or a repeated word, stops start-up with `AccessWordError`.

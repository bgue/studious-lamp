"""The commands the engineering module offers to the API (brief 11.1, 25.2; P1-I1).

The API builds one ``POST /commands/<Name>`` route per row. ``access`` says who may call it:

* ``admin``: the registry and the tag classes are company data, so only an admin;
* ``company``: a code value is company data in ``company`` scope (admin) and a project's own value
  in a project scope (any signed-in person);
* ``user``: a tag is a project record, so any signed-in person.

``SplitTag`` is not offered over HTTP: it returns several results, and the command table answers
with exactly one. Use ``tl tag split`` for it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

from tl_mod_engineering.handlers.standards import (
    AddCodeValue,
    CloseCodeValue,
    CloseStandard,
    RegisterCodeList,
    RegisterMnemonic,
    RegisterNumberingPattern,
    handle_add_code_value,
    handle_close_code_value,
    handle_close_standard,
    handle_register_code_list,
    handle_register_mnemonic,
    handle_register_numbering_pattern,
)
from tl_mod_engineering.handlers.tag_class import (
    CloseTagClass,
    DefineTagClass,
    ReviseTagClass,
    handle_close_tag_class,
    handle_define_tag_class,
    handle_revise_tag_class,
)
from tl_mod_engineering.handlers.tags import (
    CreateTag,
    MergeTags,
    ReclassifyTag,
    RenameTag,
    handle_create_tag,
    handle_merge_tags,
    handle_reclassify_tag,
    handle_rename_tag,
)

Access = Literal["admin", "company", "user"]


@dataclass(frozen=True)
class ApiCommand:
    model: type[Command]
    handler: Callable[[UnitOfWork, Any], CommandResult]
    access: Access


API_COMMANDS: tuple[ApiCommand, ...] = (
    ApiCommand(RegisterCodeList, handle_register_code_list, "admin"),
    ApiCommand(RegisterMnemonic, handle_register_mnemonic, "admin"),
    ApiCommand(RegisterNumberingPattern, handle_register_numbering_pattern, "admin"),
    ApiCommand(CloseStandard, handle_close_standard, "admin"),
    ApiCommand(AddCodeValue, handle_add_code_value, "company"),
    ApiCommand(CloseCodeValue, handle_close_code_value, "company"),
    ApiCommand(DefineTagClass, handle_define_tag_class, "admin"),
    ApiCommand(ReviseTagClass, handle_revise_tag_class, "admin"),
    ApiCommand(CloseTagClass, handle_close_tag_class, "admin"),
    ApiCommand(CreateTag, handle_create_tag, "user"),
    ApiCommand(ReclassifyTag, handle_reclassify_tag, "user"),
    ApiCommand(RenameTag, handle_rename_tag, "user"),
    ApiCommand(MergeTags, handle_merge_tags, "user"),
)

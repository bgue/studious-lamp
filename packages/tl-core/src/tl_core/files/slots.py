"""File slots (brief 20.1, ``tl:file_slots``): what a record type accepts as attachments.

A slot is declared on a LinkML class with the ``tl:file_slots`` annotation (see
``schema/core/annotations.yaml``) and read here as plain YAML, the same way expected links are. The
upload service checks a file against its slot before accepting it; the workflow layer asks which
required slots are still empty. A file with no slot is a generic attachment and needs no
declaration.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from tl_schema.registry import default_schema_dir


class FileSlot(BaseModel):
    """One declared slot."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str | None = None
    cardinality: Literal["one", "many"] = "many"
    accepted_types: list[str] = []  # media types, ``image/*`` wildcards allowed; empty means any
    max_size: int | None = Field(default=None, ge=1)  # bytes; None means no slot limit
    required_in_states: list[str] = []  # workflow states by which the slot needs an available file
    capture_hint: Literal["camera", "scan", "file"] = "file"
    metadata_pset: str | None = None
    processing: list[str] = []
    retention_class: str | None = None
    confidentiality: str | None = None

    @property
    def display(self) -> str:
        """``label`` when given, else the slot name."""
        return self.label or self.name

    def accepts(self, content_type: str) -> bool:
        """Whether a media type fits ``accepted_types`` (parameters after ``;`` are ignored)."""
        if not self.accepted_types:
            return True
        media = content_type.split(";", 1)[0].strip().lower()
        return any(fnmatchcase(media, pattern.strip().lower()) for pattern in self.accepted_types)


class FileSlotError(ValueError):
    """A slot declaration that cannot be read. The message names the source."""


class FileSlotRegistry:
    """Slots by record type (``core.Record``), in declaration order."""

    def __init__(self, by_type: Mapping[str, Sequence[FileSlot]] | None = None) -> None:
        self._by_type: dict[str, list[FileSlot]] = {}
        for record_type, slots in (by_type or {}).items():
            for slot in slots:
                self.add(record_type, slot)

    def add(self, record_type: str, slot: FileSlot) -> None:
        """Declare a slot. A second slot with the same name on a type raises ``FileSlotError``."""
        existing = self._by_type.setdefault(record_type, [])
        if any(s.name == slot.name for s in existing):
            raise FileSlotError(f"{record_type}: slot {slot.name!r} is declared twice")
        existing.append(slot)

    def for_type(self, record_type: str) -> list[FileSlot]:
        """The slots of a record type (a new list; empty when there are none)."""
        return list(self._by_type.get(record_type, []))

    def get(self, record_type: str, name: str) -> FileSlot | None:
        """One slot by name, or ``None``."""
        for slot in self._by_type.get(record_type, []):
            if slot.name == name:
                return slot
        return None

    def record_types(self) -> list[str]:
        """Record types that declare at least one slot, sorted."""
        return sorted(record_type for record_type, slots in self._by_type.items() if slots)

    def merge(self, other: FileSlotRegistry) -> None:
        """Add every slot of ``other``; a name clash on a type raises ``FileSlotError``."""
        for record_type, slots in other._by_type.items():
            for slot in slots:
                self.add(record_type, slot)


def _as_mapping(value: object) -> dict[str, Any] | None:
    """``value`` as a mapping, or None when it is not one."""
    if not isinstance(value, dict):
        return None
    return cast(dict[str, Any], value)


def parse_file_slots(text: str, *, source: str = "<string>") -> FileSlotRegistry:
    """Read the ``tl:file_slots`` annotations of every class in one LinkML YAML document.

    The record type of a class is ``<module>.<ClassName>`` where ``<module>`` is the schema-level
    annotation ``tl:module``. The annotation value is a list of mappings (see ``FileSlot``); a
    single mapping is also accepted. An empty file declares nothing. Raises ``FileSlotError``
    (message starts with ``source``) for the cases listed in the ticket.
    """
    try:
        loaded: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise FileSlotError(f"{source}: invalid YAML: {exc}") from exc
    registry = FileSlotRegistry()
    if loaded is None:
        return registry  # an empty file declares nothing
    document = _as_mapping(loaded)
    if document is None:
        raise FileSlotError(f"{source}: a schema file must be a YAML mapping")
    classes = _as_mapping(document.get("classes"))
    if classes is None:
        return registry
    schema_annotations = _as_mapping(document.get("annotations"))
    module: Any = schema_annotations.get("tl:module") if schema_annotations is not None else None
    for class_key, class_value in classes.items():
        class_name = str(class_key)
        class_def = _as_mapping(class_value)
        if class_def is None:
            continue
        class_annotations = _as_mapping(class_def.get("annotations"))
        if class_annotations is None or "tl:file_slots" not in class_annotations:
            continue
        if not isinstance(module, str) or not module:
            raise FileSlotError(
                f"{source}: class {class_name} has tl:file_slots but the schema has no tl:module"
            )
        entries: Any = class_annotations["tl:file_slots"]
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            raise FileSlotError(
                f"{source}: {class_name}.tl:file_slots must be a mapping or a list of mappings"
            )
        for index, entry in enumerate(cast(list[Any], entries)):
            try:
                slot = FileSlot.model_validate(entry)
            except ValidationError as exc:
                problems = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
                )
                raise FileSlotError(
                    f"{source}: {class_name}.tl:file_slots[{index}]: {problems}"
                ) from exc
            try:
                registry.add(f"{module}.{class_name}", slot)
            except FileSlotError as exc:
                raise FileSlotError(f"{source}: {exc}") from exc
    return registry


def load_file_slots(path: Path) -> FileSlotRegistry:
    """Read one YAML file, or every ``*.yaml`` file of a directory (not recursive, sorted by name).

    A missing path gives an empty registry.
    """
    registry = FileSlotRegistry()
    if path.is_dir():
        files = sorted((p for p in path.glob("*.yaml") if p.is_file()), key=lambda p: p.name)
    elif path.is_file():
        files = [path]
    else:
        return registry
    for file in files:
        try:
            content = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise FileSlotError(f"{file.name}: cannot read file: {exc}") from exc
        parsed = parse_file_slots(content, source=file.name)
        try:
            registry.merge(parsed)
        except FileSlotError as exc:
            raise FileSlotError(f"{file.name}: {exc}") from exc
    return registry


def default_file_slots() -> FileSlotRegistry:
    """The slots in ``<schema dir>/files`` (``TL_SCHEMA_DIR`` or ``schema/fixtures``)."""
    return load_file_slots(default_schema_dir() / "files")

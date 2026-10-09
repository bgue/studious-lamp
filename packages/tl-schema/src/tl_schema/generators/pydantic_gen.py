# pyright: basic
"""Pydantic v2 models from the core LinkML schema."""

from __future__ import annotations

from contextlib import chdir
from pathlib import Path

from linkml.generators.pydanticgen import PydanticGenerator

ROOT_SCHEMA = "core.yaml"


def generate(schema_dir: Path) -> dict[str, str]:
    """Return {path relative to generated/: file text}. Runs inside schema_dir."""
    with chdir(schema_dir):
        text = PydanticGenerator(ROOT_SCHEMA).serialize()
    return {"models.py": text}

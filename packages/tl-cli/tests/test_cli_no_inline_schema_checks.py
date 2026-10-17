"""No CLI command runs a JSON Schema itself: the check goes through the envelope (ADR-0014).

A schema's patterns are a person's input; running them in the CLI process would put the denial of
service the envelope exists to stop back in the command. The commands read the stored report or
call ``views.validate_stored``, which validates in a child process (security re-review of b5f5d41).
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "tl_cli"


def test_no_command_imports_jsonschema_or_the_in_process_validator() -> None:
    offenders: list[str] = []
    for path in sorted(SRC.glob("*.py")):
        text = path.read_text()
        for needle in ("import jsonschema", "from jsonschema", "validate_against_schema_inline"):
            if needle in text:
                offenders.append(f"{path.name}: {needle}")
    assert offenders == []


def test_the_check_command_names_the_envelope_backed_view() -> None:
    text = (SRC / "derive_read.py").read_text()
    assert "views.validate_stored" in text

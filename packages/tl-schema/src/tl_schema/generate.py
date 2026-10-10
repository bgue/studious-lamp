"""Run every schema generator and write the outputs under ``generated/``.

``just gen`` writes the generated files; ``just check`` runs ``--check``, which exits non-zero when
the committed generated files differ from what the generators would write. ``--check`` never
modifies files.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from tl_schema.generators import catalog, ddl, jsonschema_gen, pydantic_gen

GENERATED_DIR: Path = Path(__file__).resolve().parent / "generated"
SCHEMA_DIR: Path = Path(__file__).resolve().parents[4] / "schema" / "core"
GENERATORS: list[Callable[[Path], dict[str, str]]] = [
    pydantic_gen.generate,
    jsonschema_gen.generate,
    ddl.generate,
    catalog.generate,
]

INIT_TEXT = '"""Generated from schema/ by `just gen`. Do not edit by hand."""\n'


def _normalise(text: str) -> str:
    return text.rstrip("\n") + "\n"


def outputs(schema_dir: Path = SCHEMA_DIR) -> dict[str, str]:
    """Run every generator. Keys are posix paths relative to generated/, sorted.

    Always includes "__init__.py" with the text
    '\"\"\"Generated from schema/ by `just gen`. Do not edit by hand.\"\"\"\n'.
    Every value is normalised to end with exactly one newline.
    """
    collected: dict[str, str] = {"__init__.py": INIT_TEXT}
    for generator in GENERATORS:
        collected.update(generator(schema_dir))
    return {path: _normalise(collected[path]) for path in sorted(collected)}


def existing(out_dir: Path) -> set[str]:
    """Posix paths of every file under out_dir.

    Ignores any __pycache__ directory; returns an empty set if out_dir is absent.
    """
    if not out_dir.is_dir():
        return set()
    found: set[str] = set()
    for path in out_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(out_dir)
        if "__pycache__" in relative.parts:
            continue
        found.add(relative.as_posix())
    return found


def problems(out_dir: Path, files: dict[str, str]) -> list[str]:
    """Return lines 'missing: <path>', 'differs: <path>', 'stale: <path>'.

    A stale line is a file on disk that is not in files. An empty list means in sync.
    """
    on_disk = existing(out_dir)
    lines: list[str] = []
    for path in sorted(files):
        if path not in on_disk:
            lines.append(f"missing: {path}")
            continue
        current = (out_dir / path).read_bytes().decode("utf-8")
        if current != files[path]:
            lines.append(f"differs: {path}")
    for path in sorted(on_disk - set(files)):
        lines.append(f"stale: {path}")
    return lines


def write(out_dir: Path, files: dict[str, str]) -> None:
    """Delete stale files, create parent directories, write every file as UTF-8."""
    for path in existing(out_dir) - set(files):
        (out_dir / path).unlink()
    for path, text in files.items():
        target = out_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    """Run the generators; write the output, or verify it with --check.

    Flags: --check (verify only), --out DIR (default GENERATED_DIR), --schema-dir DIR
    (default SCHEMA_DIR).

    Without --check: write and print 'wrote N files to <out>', return 0.
    With --check: print each problem to stderr, then
    'codegen drift: run `just gen` and commit the result' to stderr and return 1 when there are
    problems; otherwise print 'generated files are up to date (N files)' and return 0.
    """
    parser = argparse.ArgumentParser(prog="python -m tl_schema.generate")
    parser.add_argument("--check", action="store_true", help="verify only; do not write")
    parser.add_argument("--out", type=Path, default=GENERATED_DIR, help="output directory")
    parser.add_argument(
        "--schema-dir", type=Path, default=SCHEMA_DIR, help="LinkML schema root directory"
    )
    args = parser.parse_args(argv)
    out_dir: Path = args.out
    schema_dir: Path = args.schema_dir
    files = outputs(schema_dir)

    if args.check:
        found = problems(out_dir, files)
        if found:
            for line in found:
                print(line, file=sys.stderr)
            print("codegen drift: run `just gen` and commit the result", file=sys.stderr)
            return 1
        print(f"generated files are up to date ({len(files)} files)")
        return 0

    write(out_dir, files)
    print(f"wrote {len(files)} files to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

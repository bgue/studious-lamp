#!/usr/bin/env python3
"""Secret scan over the files git tracks (04-gates section 1 "Security scan"; AGENTS.md rule 10).

    uv run python dev/tools/scan_secrets.py

Looks for private-key blocks and the token shapes of common services. It is a tripwire, not a
vault: a finding is either a real secret to remove and rotate, or a documented example that belongs
in ``ALLOWED`` with a reason. Exit code 1 when there is a finding.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PATTERNS = {
    "private key block": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
    "AWS access key id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "API key (sk- style)": re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
}
ALLOWED: dict[str, str] = {
    # "path:pattern name": "why this is not a secret"
}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".parquet", ".ico", ".svg", ".lock"}


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode()
    return [ROOT / name for name in out.split("\0") if name]


def scan() -> list[str]:
    findings: list[str] = []
    for path in tracked_files():
        if path.suffix.lower() in SKIP_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        relative = path.relative_to(ROOT).as_posix()
        for name, pattern in PATTERNS.items():
            if f"{relative}:{name}" in ALLOWED:
                continue
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{relative}:{line}: {name}")
    return findings


def main() -> int:
    findings = scan()
    for finding in findings:
        print(finding)
    print(f"{len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())

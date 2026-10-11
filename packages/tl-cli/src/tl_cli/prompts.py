"""Reading a password for the CLI without putting it on a command line.

A password is never an option or an argument: it would show in `ps` and in shell history. The
choices are a hidden prompt (twice when ``confirm``) or one line from standard input.
"""

from __future__ import annotations

import sys

import typer

from tl_cli.session import fail


def read_password(*, from_stdin: bool, confirm: bool = False, prompt: str = "Password") -> str:
    """One password: a line of standard input, or a hidden prompt (twice if ``confirm``)."""
    if from_stdin:
        line = sys.stdin.readline()
        value = line.rstrip("\r\n")
        if not value:
            fail("no password on standard input")
        return value
    value = typer.prompt(prompt, hide_input=True)
    if confirm and typer.prompt(f"Repeat {prompt.lower()}", hide_input=True) != value:
        fail("the two passwords differ")
    return str(value)

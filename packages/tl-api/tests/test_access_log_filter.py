"""The access-log filter: a scan code never reaches a handler of ``uvicorn.access``."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from tl_api.main import ScanCodeRedactor, install_access_log_filter, redact_code_paths

CODE = "ABCDEFGH23456789"


class Keep(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@pytest.fixture
def lines() -> Iterator[list[str]]:
    access = logging.getLogger("uvicorn.access")
    before = list(access.filters)
    handler = Keep()
    access.addHandler(handler)
    access.setLevel(logging.INFO)
    install_access_log_filter()
    try:
        yield handler.lines
    finally:
        access.removeHandler(handler)
        access.filters[:] = before


def log(path: str, status: int = 200) -> None:
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d', "127.0.0.1:5000", "GET", path, "1.1", status
    )


@pytest.mark.parametrize(
    ("path", "shown"),
    [
        (f"/web/q/{CODE}", "/web/q/<redacted>"),
        (f"/web/q/{CODE.lower()}", "/web/q/<redacted>"),
        ("/web/q/anything-at-all", "/web/q/<redacted>"),
        (f"/qr/resolve/{CODE}", "/qr/resolve/<redacted>"),
        (f"/qr/resolve/{CODE}?x=1", "/qr/resolve/<redacted>?x=1"),
        (f"/web/sign-in?next=/web/q/{CODE}", "/web/sign-in?next=/web/q/<redacted>"),
        (f"/web/sign-in?next=%2Fweb%2Fq%2F{CODE}", "/web/sign-in?next=%2Fweb%2Fq%2F<redacted>"),
    ],
)
def test_a_code_in_the_path_is_redacted(lines: list[str], path: str, shown: str) -> None:
    log(path, 404)
    assert lines == [f'127.0.0.1:5000 - "GET {shown} HTTP/1.1" 404']
    assert CODE not in lines[0] and CODE.lower() not in lines[0]


@pytest.mark.parametrize(
    "path",
    [
        "/web/q",
        "/web/p/P123/rfis",
        "/qr/codes?record=K-1",
        "/health",
        "/web/sign-in",
        "/qr/resolve",
    ],
)
def test_any_other_path_is_untouched_byte_for_byte(lines: list[str], path: str) -> None:
    log(path)
    assert lines == [f'127.0.0.1:5000 - "GET {path} HTTP/1.1" 200']
    assert redact_code_paths(path) == path


def test_the_record_args_are_rewritten_before_a_handler_formats_them() -> None:
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, "f", 1, '%s "%s"', ("a", f"/web/q/{CODE}"), None
    )
    assert ScanCodeRedactor().filter(record) is True
    assert record.args == ("a", "/web/q/<redacted>")
    same = logging.LogRecord("uvicorn.access", logging.INFO, "f", 1, "%s", ("/health",), None)
    ScanCodeRedactor().filter(same)
    assert same.args == ("/health",)


def test_it_is_installed_once() -> None:
    access = logging.getLogger("uvicorn.access")
    before = list(access.filters)
    try:
        install_access_log_filter()
        install_access_log_filter()
        assert sum(isinstance(f, ScanCodeRedactor) for f in access.filters) == 1
    finally:
        access.filters[:] = before

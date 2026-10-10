"""``split_url``: libpq-style query parameters become driver arguments (no database needed)."""

from __future__ import annotations

import ssl

import pytest
from tl_adapters.postgres.engine import split_url

BASE = "postgresql://u:p@localhost:5432/db"


def test_sslmode_disable_turns_tls_off_and_leaves_the_url_clean() -> None:
    parsed, args = split_url(BASE + "?sslmode=disable")
    assert args == {"ssl_context": False}
    assert "sslmode" not in parsed.query


def test_require_encrypts_without_checking_the_certificate() -> None:
    parsed, args = split_url(BASE + "?sslmode=require")
    context = args["ssl_context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_NONE and context.check_hostname is False
    assert "sslmode" not in parsed.query


def test_verify_ca_checks_the_chain_but_not_the_host_name() -> None:
    context = split_url(BASE + "?sslmode=verify-ca")[1]["ssl_context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is False


def test_verify_full_checks_chain_and_host_name() -> None:
    context = split_url(BASE + "?sslmode=verify-full")[1]["ssl_context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True


@pytest.mark.parametrize("mode", ["allow", "prefer", "nonsense"])
def test_any_other_sslmode_is_refused_not_guessed(mode: str) -> None:
    with pytest.raises(ValueError, match="disable, require, verify-ca, verify-full"):
        split_url(BASE + f"?sslmode={mode}")


def test_sslmode_combines_with_the_schema_option() -> None:
    _, args = split_url(BASE + "?sslmode=disable&options=-csearch_path%3Dtl_t_1")
    assert args["ssl_context"] is False
    assert args["startup_params"] == {"search_path": "tl_t_1"}


def test_no_query_means_no_extra_arguments() -> None:
    assert split_url(BASE)[1] == {}

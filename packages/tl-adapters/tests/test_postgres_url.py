"""``split_url``: libpq-style query parameters become driver arguments (no database needed)."""

from __future__ import annotations

from tl_adapters.postgres.engine import split_url

BASE = "postgresql://u:p@localhost:5432/db"


def test_sslmode_disable_turns_tls_off_and_leaves_the_url_clean() -> None:
    parsed, args = split_url(BASE + "?sslmode=disable")
    assert args == {"ssl_context": False}
    assert "sslmode" not in parsed.query


def test_another_sslmode_is_dropped_and_the_driver_default_stays() -> None:
    parsed, args = split_url(BASE + "?sslmode=require")
    assert args == {}
    assert "sslmode" not in parsed.query


def test_sslmode_combines_with_the_schema_option() -> None:
    _, args = split_url(BASE + "?sslmode=disable&options=-csearch_path%3Dtl_t_1")
    assert args["ssl_context"] is False
    assert args["startup_params"] == {"search_path": "tl_t_1"}


def test_no_query_means_no_extra_arguments() -> None:
    assert split_url(BASE)[1] == {}

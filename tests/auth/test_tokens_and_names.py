"""Token formats (ADR-0009 sections 4 and 5), usernames and the environment gates."""

from __future__ import annotations

import base64

import pytest
from tl_core.auth import env, names, tokens
from tl_core.auth.errors import InvalidAccountError


def test_tokens_carry_256_bits_and_a_kind_prefix() -> None:
    session, agent = tokens.new_session_token(), tokens.new_agent_token()
    assert session.startswith("tls_") and agent.startswith("tla_")
    for token, prefix in ((session, "tls_"), (agent, "tla_")):
        body = token.removeprefix(prefix)
        assert len(body) == 43
        raw = base64.urlsafe_b64decode(body + "=")
        assert len(raw) == 32
    assert tokens.token_kind(session) == "session" and tokens.token_kind(agent) == "agent"


def test_tokens_do_not_repeat() -> None:
    assert len({tokens.new_session_token() for _ in range(500)}) == 500


def test_only_the_sha256_is_a_stored_form_and_it_differs_from_the_token() -> None:
    token = tokens.new_session_token()
    digest = tokens.token_hash(token)
    assert len(digest) == 64 and token not in digest and digest == tokens.token_hash(token)
    assert tokens.token_hash(token + "x") != digest


@pytest.mark.parametrize(
    "value", ["", "nope", "Bearer tls_x", "tls", "x" * 500, "tls_" + "x" * 500, "\ud800"]
)
def test_values_that_are_not_ours_have_no_kind(value: str) -> None:
    assert tokens.token_kind(value) is None


def test_hashing_a_lone_surrogate_does_not_raise() -> None:
    assert len(tokens.token_hash("tls_\ud800")) == 64


def test_usernames_are_normalised_and_checked() -> None:
    assert names.check_username("Alice") == "alice"
    assert names.check_username("ＢＯＢ") == "bob"  # NFKC folds full-width letters
    assert names.check_username("a.b-c_d@e") == "a.b-c_d@e"
    for bad in ("", " alice", "-lead", "a b", "a/b", "x" * 65, "аlice", "al\x00ice"):
        with pytest.raises(InvalidAccountError):
            names.check_username(bad)


def test_the_username_key_is_the_normalised_name_cut_to_64() -> None:
    assert names.username_key("ALICE") == "alice"
    assert len(names.username_key("A" * 200)) == 64


def test_actors_follow_the_kind() -> None:
    assert names.actor_for("person", "alice") == "user:alice"
    assert names.actor_for("sim", "sim-1") == "user:sim-1"
    assert names.actor_for("agent", "triage") == "agent:triage"


def test_display_names_and_labels_are_bounded_and_clean() -> None:
    assert names.check_text("  Alice A  ", what="display name", limit=10) == "Alice A"
    for bad in ("", "   ", "x" * 11, "a\x07b", "a\nb"):
        with pytest.raises(InvalidAccountError):
            names.check_text(bad, what="display name", limit=10)


@pytest.mark.parametrize(
    ("value", "tokens_ok", "demo_ok"),
    [
        ("dev", True, True),
        ("test", True, True),
        ("ci", True, False),
        ("demo", False, True),
        ("prod", False, False),
        ("production", False, False),
        ("", False, False),
        ("DEV", True, True),
    ],
)
def test_the_environment_gates_fail_closed(value: str, tokens_ok: bool, demo_ok: bool) -> None:
    assert env.dev_tokens_allowed(value) is tokens_ok
    assert env.demo_allowed(value) is demo_ok
    assert env.dev_tokens_allowed({"TL_ENV": value}) is tokens_ok


def test_an_unset_environment_allows_neither() -> None:
    assert env.dev_tokens_allowed({}) is False
    assert env.demo_allowed({}) is False

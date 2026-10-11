"""Password hashing and policy (ADR-0009 sections 2 and 3): no database needed."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from tl_core.auth import password as pw
from tl_core.auth.errors import WeakPasswordError

GOOD = "correct horse battery"


@pytest.fixture
def scrypt_calls(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[pw.ScryptParams]]:
    """Every scrypt the module runs, so a test can prove work was done."""
    calls: list[pw.ScryptParams] = []
    real = pw._scrypt  # pyright: ignore[reportPrivateUsage]

    def counting(password: str, salt: bytes, params: pw.ScryptParams) -> bytes:
        calls.append(params)
        return real(password, salt, params)

    monkeypatch.setattr(pw, "_scrypt", counting)
    yield calls


def test_a_hash_is_self_describing_and_salted() -> None:
    first, second = pw.hash_password(GOOD), pw.hash_password(GOOD)
    assert first != second
    scheme, log2_n, r, p, salt, digest = first.split("$")
    assert (scheme, int(log2_n), int(r), int(p)) == ("scrypt", 4, 1, 1)  # the test cost
    assert salt and digest and GOOD not in first


def test_the_production_cost_is_the_owasp_profile_and_is_what_a_server_gets() -> None:
    assert pw.PRODUCTION_PARAMS == pw.ScryptParams(log2_n=16, r=8, p=2)
    previous = pw.configure(pw.PRODUCTION_PARAMS)
    try:
        stored = pw.hash_password(GOOD)
        assert stored.startswith("scrypt$16$8$2$")
        assert pw.verify_password(stored, GOOD)
        assert not pw.needs_rehash(stored)
    finally:
        pw.configure(previous)


def test_verify_accepts_the_password_and_nothing_else() -> None:
    stored = pw.hash_password(GOOD)
    assert pw.verify_password(stored, GOOD)
    assert not pw.verify_password(stored, GOOD + " ")
    assert not pw.verify_password(stored, "")
    assert not pw.verify_password(stored, GOOD.upper())


def test_equivalent_unicode_spellings_are_the_same_password() -> None:
    composed, decomposed = "café au lait 2026", "café au lait 2026"
    assert pw.verify_password(pw.hash_password(composed), decomposed)


@pytest.mark.parametrize("stored", [None, "", "x", "scrypt$4$1$1$AAAA", "md5$4$1$1$AA$AA"])
def test_verify_runs_a_full_scrypt_even_with_no_usable_hash(
    stored: str | None, scrypt_calls: list[pw.ScryptParams]
) -> None:
    assert pw.verify_password(stored, GOOD) is False
    assert len(scrypt_calls) == 1


def test_a_wrong_password_costs_the_same_one_scrypt(scrypt_calls: list[pw.ScryptParams]) -> None:
    stored = pw.hash_password(GOOD)
    scrypt_calls.clear()
    pw.verify_password(stored, "wrong password here")
    pw.verify_password(None, "wrong password here")
    assert len(scrypt_calls) == 2


def test_a_stored_hash_cannot_ask_for_more_memory_than_the_bounds(
    scrypt_calls: list[pw.ScryptParams],
) -> None:
    good = pw.hash_password(GOOD)
    _, _, r, p, salt, digest = good.split("$")
    for tampered in (
        f"scrypt$30${r}${p}${salt}${digest}",  # N = 2^30: gigabytes
        f"scrypt$4$64${p}${salt}${digest}",
        f"scrypt$4${r}$64${salt}${digest}",
        f"scrypt$0${r}${p}${salt}${digest}",
        f"scrypt$-1${r}${p}${salt}${digest}",
        f"scrypt$four${r}${p}${salt}${digest}",
    ):
        scrypt_calls.clear()
        assert pw.verify_password(tampered, GOOD) is False
        assert all(call.log2_n <= pw.MAX_LOG2_N for call in scrypt_calls)
        assert len(scrypt_calls) == 1  # only the dummy ran


def test_a_hash_with_a_short_digest_or_salt_is_refused() -> None:
    _, log2_n, r, p, salt, digest = pw.hash_password(GOOD).split("$")
    assert not pw.verify_password(f"scrypt${log2_n}${r}${p}${salt}${digest[:10]}", GOOD)
    assert not pw.verify_password(f"scrypt${log2_n}${r}${p}$AAA${digest}", GOOD)


def test_a_very_long_password_is_refused_without_hashing_all_of_it(
    scrypt_calls: list[pw.ScryptParams],
) -> None:
    stored = pw.hash_password(GOOD)
    scrypt_calls.clear()
    assert pw.verify_password(stored, "a" * 100_000) is False
    assert len(scrypt_calls) == 1


def test_needs_rehash_when_the_stored_cost_is_weaker_than_the_current() -> None:
    stored = pw.hash_password(GOOD)
    assert not pw.needs_rehash(stored)
    previous = pw.configure(pw.ScryptParams(log2_n=5, r=1, p=1))
    try:
        assert pw.needs_rehash(stored)
    finally:
        pw.configure(previous)
    assert pw.needs_rehash("garbage")


def test_configure_refuses_costs_outside_the_bounds() -> None:
    for bad in (
        pw.ScryptParams(log2_n=0),
        pw.ScryptParams(log2_n=21),
        pw.ScryptParams(r=17),
        pw.ScryptParams(p=0),
    ):
        with pytest.raises(ValueError):
            pw.configure(bad)


def test_hashing_is_limited_to_a_few_at_once() -> None:
    assert pw.MAX_CONCURRENT_HASHES == 4


def test_the_policy_accepts_a_long_passphrase() -> None:
    pw.check_policy(GOOD, username="alice")
    pw.check_policy("p" * 12 + "q")


@pytest.mark.parametrize(
    ("candidate", "expect"),
    [
        ("short", "at least 12"),
        ("x" * 129, "at most 128"),
        ("aaaaaaaaaaaaaaaa", "repeated"),
        ("Password1234", "common"),
        ("QWERTYUIOP12", "common"),
        ("alice.the.admin", "username"),
        ("has a\x00nul inside", "control"),
        ("tab\tinside password", "control"),
    ],
)
def test_the_policy_names_the_rule_and_never_echoes_the_password(
    candidate: str, expect: str
) -> None:
    username = "alice.the.admin"
    with pytest.raises(WeakPasswordError) as raised:
        pw.check_policy(candidate, username=username)
    assert any(expect in issue for issue in raised.value.issues)
    assert candidate not in str(raised.value)


def test_the_policy_ignores_case_when_comparing_with_the_username() -> None:
    with pytest.raises(WeakPasswordError):
        pw.check_policy("Alice.The.Admin", username="alice.the.admin")


def test_there_are_no_composition_rules() -> None:
    pw.check_policy("all lowercase words only")
    pw.check_policy("1234567890 purple")

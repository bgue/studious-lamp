"""Intent text round-trips and the event hash over it is stable (P2-GUARD)."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from tl_core.intent import Intent, IntentRef, IntentToward, intent_json
from tl_core.ledger.hashing import event_hash

_text = st.text(min_size=1, max_size=40)
_ref = st.one_of(
    st.builds(IntentRef, command=_text, target=st.none() | _text),
    st.builds(IntentRef, text=_text),
    st.builds(IntentRef),  # empty items are dropped by the dump
)
_toward = st.builds(
    IntentToward, target=_text, state=st.none() | _text, condition=st.none() | _text
)
_intent = st.builds(
    Intent,
    why=st.none() | _text,
    next=st.lists(_ref, max_size=5),
    toward=st.none() | _toward,
    goal_ref=st.none() | st.from_regex(r"[a-z0-9_-]{1,64}", fullmatch=True),
)


@given(_intent)
def test_intent_json_round_trips(intent: Intent) -> None:
    stored = intent_json(intent)
    if stored is None:
        return
    assert intent_json(Intent.model_validate_json(stored)) == stored


@given(_intent)
def test_hash_over_intent_is_stable(intent: Intent) -> None:
    stored = intent_json(intent)
    if stored is None:
        return
    again = intent_json(Intent.model_validate_json(stored))
    assert again is not None

    def digest(text: str) -> str:
        return event_hash(
            None, "E1", "S1", 1, "Thing.Made", "{}", "2026-01-01T00:00:00+00:00", text
        )

    assert digest(stored) == digest(again)

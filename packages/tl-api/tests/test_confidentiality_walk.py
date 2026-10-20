"""ADR-0016 at the HTTP edge: a walk of every GET route as five kinds of reader (P1-I5-T06).

The ledger holds one item of each class in the correspondence module (internal, restricted,
privileged, and one with a class nobody knows), a restricted document, a thread and a clock on the
hidden items, a file on one of them, a link, a feed post that tags one, and the events they made.
Every GET route of the app is then called with every combination of the names and ids of those
records, as a plain user, a document controller, an admin, a person named on the privileged item
and an agent. A response may hold the text and ids of what the reader may read and of nothing
else. An explicit list names the one route that is not walked here (the event stream, which has its
own test) and a count assertion proves the walk found the routes (L-P1-I3-11).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from harness import SCOPE, Harness
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_mod_correspondence.confseed import TOKENS, seed_hidden_world
from tl_mod_legacy.testing import seed_restricted_run

PASSWORD = "correct horse battery"


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    """These walks run on SQLite, and on Postgres under ``--adapters sqlite,postgres``."""
    return parity_harness


#: What each reader may read, by the kinds above. The admin is a controller: no agent and no
#: privilege. Only the accounts named on a privileged item read it, the controller who set it among
#: them. A class nobody knows is read by nobody.
MAY_READ = {
    "bob": {"open"},
    "ctl": {
        "open",
        "restricted",
        "privileged",
        "document",
        "file",
        "commercial",
        "secret_rfi",
        "loadrun",
    },
    "boss": {"open", "restricted", "document", "file", "commercial", "loadrun"},
    "amy": {"open", "privileged", "secret_rfi"},
    "bot": {"open"},
}
#: Routes this file does not walk, and why. Anything else that is a GET route is walked.
NOT_WALKED = {
    "/stream": "an open stream: tests/test_confidentiality_walk.py::test_the_stream",
}
MIN_ROUTES = 70
FAKE_ID = "01J000000000000000000000"


@dataclass
class Seed:
    ids: dict[str, str]  # kind -> record id
    numbers: dict[str, str]  # kind -> number or key
    extra_ids: dict[str, str]  # thread, clock, file, post, link... by kind ("restricted_thread")
    tokens: dict[str, str]  # actor -> session or agent token


def _person(uow: Any, name: str, roles: list[str]) -> None:
    accounts.create_account(
        uow,
        username=name,
        display_name=name.title(),
        kind="person",
        roles=roles,
        password=prepare_password(PASSWORD),
        by="svc:test",
    )


def seed(h: Harness, tmp_path: Path) -> Seed:
    with h.backend(False) as uow:
        _person(uow, "bob", ["user"])
        _person(uow, "ctl", ["document_controller"])
        _person(uow, "boss", ["admin"])
        _person(uow, "amy", ["user"])
        bot = accounts.create_account(
            uow, username="bot", display_name="Bot", kind="agent", roles=["user"], password=None,
            by="svc:test",
        )  # fmt: skip
        _, agent_token = accounts.issue_agent_token(
            uow,
            account_id=bot.account_id,
            label="walk",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            by="svc:test",
        )
    tokens = {
        name: sessions.sign_in(h.backend, username=name, password=PASSWORD)[1]
        for name in ("bob", "ctl", "boss", "amy")
    }
    tokens["bot"] = agent_token

    hidden = seed_hidden_world(h.target or h.db, h.service, tmp_path)
    run_id, run_files = seed_restricted_run(h.target or h.db, h.service)
    hidden.ids["loadrun"] = run_id
    hidden.extra_ids.update({f"loadrun_{slot}_file": fid for slot, fid in run_files.items()})
    return Seed(hidden.ids, hidden.numbers, hidden.extra_ids, tokens)


def hidden_markers(seed_data: Seed, reader: str) -> tuple[list[str], list[str]]:
    """(tokens, ids) the reader must never see in any response."""
    may = MAY_READ[reader]
    tokens = [t for kind, t in TOKENS.items() if kind not in may]
    ids: list[str] = []
    for kind in (
        "restricted",
        "privileged",
        "bogus",
        "document",
        "commercial",
        "secret_rfi",
        "loadrun",
    ):
        if kind in may:
            continue
        ids.append(seed_data.ids[kind])
        ids += [v for k, v in seed_data.extra_ids.items() if k.startswith(f"{kind}_")]
    if "restricted" not in may:  # the link and its post hang on the restricted item
        ids.append(seed_data.extra_ids["link"])
    return tokens, ids


@pytest.fixture
def seeded(harness: Harness, tmp_path: Path) -> Seed:
    return seed(harness, tmp_path)


def candidates(seed_data: Seed) -> dict[str, list[str]]:
    all_ids = [*seed_data.ids.values(), *seed_data.extra_ids.values()]
    return {
        "project": ["P123"],
        "number": [*seed_data.numbers.values(), "P123-THR-0001", "P123-THR-0002"],
        "record_id": all_ids,
        "clock_id": [v for k, v in seed_data.extra_ids.items() if k.endswith("_clock")],
        "post_id": [v for k, v in seed_data.extra_ids.items() if k.endswith("_post")],
        "file_id": [v for k, v in seed_data.extra_ids.items() if k.endswith("_file")],
        "code": ["MER", "x"],
        "ref": all_ids[:3],
        "job_id": all_ids[:2],
        "proposal_id": [v for k, v in seed_data.extra_ids.items() if k.endswith("_proposal")],
        "account_id": all_ids[:1],
        "name": ["x"],
        "key": ["x"],
        "kind": ["x"],
        "type_ref": ["x"],
        "activity_id": ["x", *all_ids[:2]],
    }


def query_variants(seed_data: Seed, names: list[str]) -> list[dict[str, str]]:
    base = {"scope": SCOPE} if "scope" in names else {}
    out: list[dict[str, str]] = [base]
    if "record_id" in names:
        out += [{**base, "record_id": i} for i in seed_data.ids.values()]
    if "q" in names:
        out += [{**base, "q": t} for t in TOKENS.values()]
    if "key" in names:
        out += [{**base, "key": n} for n in seed_data.numbers.values()]
    if "exclude_id" in names:
        out += [{**base, "q": "TOKEN", "exclude_id": seed_data.ids["open"]}]
    if "include_linked" in names:
        out += [{**base, "record_id": seed_data.ids["open"], "include_linked": "true"}]
    if "subject" in names:
        out += [{**base, "subject": "x"}]
    if "from" in names:
        out += [{**base, "from": "A", "to": "B"}]
    if "left" in names:
        out += [{**base, "left": "project", "right": "company"}]
    return out


def get_routes(h: Harness) -> list[tuple[str, list[str], list[str]]]:
    found: list[tuple[str, list[str], list[str]]] = []
    for path, ops in sorted(h.app.openapi()["paths"].items()):
        op = ops.get("get")
        if op is None:
            continue
        params = op.get("parameters", [])
        found.append(
            (
                path,
                [p["name"] for p in params if p["in"] == "path"],
                [p["name"] for p in params if p["in"] == "query"],
            )
        )
    return found


def test_the_walk_finds_the_routes_and_the_seed_is_what_the_walk_assumes(
    harness: Harness, seeded: Seed
) -> None:
    routes = get_routes(harness)
    assert len(routes) >= MIN_ROUTES
    paths = {p for p, _, _ in routes}
    assert {"/records/{record_id}", "/feed", "/events", "/files/{file_id}/content"} <= paths
    assert "/projects/{project}/correspondence/{number}" in paths and set(NOT_WALKED) <= paths
    # the seed: a controller sees all but the unknown class; a user sees the internal item only
    ctl = harness.client_for(None)
    ok = ctl.get(
        f"/projects/P123/correspondence/{seeded.numbers['restricted']}",
        headers={"Authorization": f"Bearer {seeded.tokens['ctl']}"},
    )
    assert ok.status_code == 200 and TOKENS["restricted"] in ok.text
    no = ctl.get(
        f"/projects/P123/correspondence/{seeded.numbers['restricted']}",
        headers={"Authorization": f"Bearer {seeded.tokens['bob']}"},
    )
    assert no.status_code == 404 and TOKENS["restricted"] not in no.text
    gone = ctl.get(
        f"/projects/P123/correspondence/{seeded.numbers['bogus']}",
        headers={"Authorization": f"Bearer {seeded.tokens['boss']}"},
    )
    assert gone.status_code == 404  # a class nobody knows is read by nobody, an admin included


def test_the_rfi_and_commercial_routes_show_each_reader_only_what_they_may_read(
    harness: Harness, seeded: Seed
) -> None:
    """P1-I6: the walk below proves nothing leaks; this proves the readable part is there."""
    client = harness.client_for(None)

    def get(reader: str, path: str) -> Any:
        return client.get(path, headers={"Authorization": f"Bearer {seeded.tokens[reader]}"})

    rfi, comm, secret = (seeded.numbers[k] for k in ("open_rfi", "commercial", "secret_rfi"))
    for reader in MAY_READ:  # the RFI is internal: everybody reads it, and its log line
        assert get(reader, f"/projects/P123/rfis/{rfi}").status_code == 200, reader
        assert rfi in get(reader, "/projects/P123/rfis").text, reader
    for reader, may in MAY_READ.items():
        for number, kind, route in (
            (comm, "commercial", "commercial"),
            (secret, "secret_rfi", "rfis"),
        ):
            found = get(reader, f"/projects/P123/{route}/{number}")
            unknown = get(reader, f"/projects/P123/{route}/{number[:-4]}0099")
            if kind in may:
                assert found.status_code == 200, (reader, number)
                continue
            assert found.status_code == unknown.status_code == 404, (reader, number)
            assert found.json()["message"].replace(number, "X") == unknown.json()[
                "message"
            ].replace(number[:-4] + "0099", "X"), reader
            assert number not in get(reader, f"/projects/P123/{route}").text, (reader, number)
    # the evidence trail of the RFI leads to the early warning for those who may read it only
    for reader, may in MAY_READ.items():
        trail = get(reader, f"/projects/P123/correspondence/{rfi}/evidence")
        assert trail.status_code == 200, reader
        assert (comm in trail.text) == ("commercial" in may), reader
        assert (secret in trail.text) is False, reader


def feed_cards(client: Any, token: str) -> list[dict[str, Any]]:
    """Every card of the project's feed that the token's reader is given, page by page."""
    cards: list[dict[str, Any]] = []
    before_seq: int | None = None
    for _ in range(20):
        query: dict[str, Any] = {"scope": SCOPE, "item_type": "card", "limit": 200}
        if before_seq is not None:
            query["before_seq"] = before_seq
        page = client.get(
            "/feed", params=query, headers={"Authorization": f"Bearer {token}"}
        ).json()
        cards += page["items"]
        before_seq = page.get("next_before")
        if before_seq is None:
            break
    return cards


@pytest.mark.parametrize("reader", sorted(MAY_READ))
def test_the_feed_cards_do_not_tell_a_reader_what_happened_to_what_they_may_not_read(
    harness: Harness, seeded: Seed, reader: str
) -> None:
    """A card's summary names the kind of record and the act, not a token: "ctl defined a
    commercial" or "ctl clearancegranted 2 correspondence" says that a hidden item exists, and so
    does "svc:scanner processed a file" for the file of a restricted item."""
    client = harness.client_for(None)
    cards = feed_cards(client, seeded.tokens[reader])
    assert cards, reader  # the open items make cards for everybody
    said = " ".join(str(card["summary"]) for card in cards).lower()
    assert ("commercial" in said) == ("commercial" in MAY_READ[reader]), (reader, said)
    assert ("clearancegranted" in said) == ("secret_rfi" in MAY_READ[reader]), (reader, said)

    def scans(found: list[dict[str, Any]]) -> int:
        return sum(1 for card in found if "processed" in str(card["summary"]).lower())

    plain = scans(feed_cards(client, seeded.tokens["bob"]))
    mine = scans(cards)
    assert plain > 0
    # the readers of the restricted file are given its scan card, nobody else
    assert (mine > plain) if "file" in MAY_READ[reader] else (mine == plain), (reader, mine, plain)


@pytest.mark.parametrize("reader", sorted(MAY_READ))
def test_no_get_route_shows_a_reader_what_they_may_not_read(
    harness: Harness, seeded: Seed, reader: str
) -> None:
    client = harness.client_for(None)
    headers = {"Authorization": f"Bearer {seeded.tokens[reader]}"}
    tokens, ids = hidden_markers(seeded, reader)
    cands = candidates(seeded)
    walked = 0
    allowed_seen = 0
    for path, path_params, query_params in get_routes(harness):
        if path in NOT_WALKED:
            continue
        for name in path_params:
            assert name in cands, f"{path}: add values for the path parameter {name!r}"
        combos = itertools.islice(itertools.product(*(cands[n] for n in path_params)), 60)
        for combo in combos:
            url = path
            for name, value in zip(path_params, combo, strict=True):
                url = url.replace("{" + name + "}", value)
            for query in query_variants(seeded, query_params):
                response = client.get(url, params=query, headers=headers)
                walked += 1
                assert response.status_code < 500, (reader, url, query, response.text[:300])
                text = response.content.decode("utf-8", errors="replace")
                for marker in [*tokens, *ids]:
                    if marker not in text:
                        continue
                    # The marker may be there only because the caller sent it (an error or a
                    # count that repeats it): the answer is then the same as for a marker that
                    # names nothing.
                    asked = f"{url} {query}"
                    assert marker in asked, (reader, url, query, marker)
                    fake_marker = FAKE_ID if marker in ids else "NOSUCHTOKEN"
                    fake_url = url.replace(marker, fake_marker)
                    fake_query = {k: v.replace(marker, fake_marker) for k, v in query.items()}
                    fake = client.get(fake_url, params=fake_query, headers=headers)
                    assert fake.status_code == response.status_code, (reader, url, query, marker)
                    assert text.replace(marker, fake_marker) == fake.content.decode(
                        "utf-8", errors="replace"
                    ), (reader, url, query, marker)
                if response.status_code == 200 and any(
                    TOKENS[k] in text for k in MAY_READ[reader] if k in TOKENS
                ):
                    allowed_seen += 1
    assert walked > 300  # the walk really made the calls
    assert allowed_seen > 5  # and the reader did see what they may read, so the check can fail


def test_a_post_that_names_a_hidden_item_does_not_resolve_the_tag(
    harness: Harness, seeded: Seed
) -> None:
    client = harness.client_for(None)
    headers = {"Authorization": f"Bearer {seeded.tokens['bob']}"}
    for kind in ("restricted", "privileged", "bogus"):
        made = client.post(
            "/commands/PostToFeed",
            json={"scope": SCOPE, "body": f"see #{seeded.numbers[kind]}"},
            headers=headers,
        )
        assert made.status_code == 200, made.text
        assert [e["event_type"] for e in made.json()["events"]] == ["Feed.Posted"]
        assert seeded.ids[kind] not in made.text


def test_commands_that_name_a_hidden_record_answer_not_found(
    harness: Harness, seeded: Seed
) -> None:
    client = harness.client_for(None)
    headers = {"Authorization": f"Bearer {seeded.tokens['bob']}"}
    for kind in ("restricted", "privileged", "bogus"):
        body: dict[str, Any] = {
            "scope": SCOPE,
            "from_id": seeded.ids["open"],
            "to_id": seeded.ids[kind],
            "relation": "references",
        }
        hidden = client.post("/commands/AddLink", json=body, headers=headers)
        unknown = client.post("/commands/AddLink", json={**body, "to_id": FAKE_ID}, headers=headers)
        assert hidden.status_code == unknown.status_code == 404
        assert hidden.json()["error"] == unknown.json()["error"]
        # the answer repeats the id the caller sent, and says nothing else
        assert hidden.text.replace(seeded.ids[kind], FAKE_ID) == unknown.text
    # the module's own commands: the same answer for a hidden item (or its clock) and for none
    for kind in ("restricted", "privileged"):
        for command, field, hidden_id in (
            ("CloseCorrespondence", "stream_id", seeded.ids[kind]),
            ("VoidDraft", "stream_id", seeded.ids[kind]),
            ("PauseClock", "clock_id", seeded.extra_ids[f"{kind}_clock"]),
        ):
            results = [
                client.post(
                    f"/commands/{command}",
                    json={"scope": SCOPE, field: sid, "reason": "x"},
                    headers=headers,
                )
                for sid in (hidden_id, FAKE_ID)
            ]
            assert [r.status_code for r in results] == [404, 404], (command, results[0].text)
            assert results[0].text.replace(hidden_id, FAKE_ID) == results[1].text


def test_the_stream(harness: Harness, seeded: Seed) -> None:
    """The open stream of events holds nothing of what the reader may not read."""
    import time

    import httpx2

    with harness.live("user:alice") as server:
        for reader in ("bob", "boss", "bot"):
            tokens, ids = hidden_markers(seeded, reader)
            text = ""
            deadline = time.monotonic() + 3
            with httpx2.Client(base_url=server.base_url, timeout=httpx2.Timeout(8)) as client:
                with client.stream(
                    "GET",
                    "/stream",
                    headers={"Authorization": f"Bearer {seeded.tokens[reader]}"},
                    params={"after": 0, "scope": SCOPE},
                ) as response:
                    assert response.status_code == 200
                    for line in response.iter_lines():
                        text += line + "\n"
                        if time.monotonic() > deadline:
                            break
            assert "event:" in text or text  # something arrived
            for token in tokens:
                assert token not in text, (reader, token)
            for hidden_id in ids:
                assert hidden_id not in text, (reader, hidden_id)


def test_the_numbers_were_allocated_by_the_numbering_counter_not_typed(
    harness: Harness, seeded: Seed
) -> None:
    assert sorted(seeded.numbers[k] for k in ("open", "restricted", "privileged", "bogus")) == [
        "P123-COR-0001",
        "P123-COR-0002",
        "P123-COR-0003",
        "P123-COR-0004",
    ]


def _answer(client: Any, command: str, body: dict[str, Any], headers: dict[str, str]) -> Any:
    return client.post(f"/commands/{command}", json={"scope": SCOPE, **body}, headers=headers)


def test_every_command_on_a_hidden_link_post_or_record_answers_as_for_nothing(
    harness: Harness, seeded: Seed
) -> None:
    """The commands that take an id (the link lifecycle, the feed, the generic record commands)
    answer a plain user the same for a hidden id as for one that names nothing: same status, same
    error, same text but for the id they sent (review of P1-I5)."""
    client = harness.client_for(None)
    headers = {"Authorization": f"Bearer {seeded.tokens['bob']}"}
    cases: list[tuple[str, str, dict[str, Any], str]] = []
    link = seeded.extra_ids["link"]
    for name, extra in (
        ("AcceptLink", {}),
        ("DeclineLink", {"reason": "x"}),
        ("RepinLink", {"pin": "A"}),
        ("VerifyLink", {}),
        ("FlagLink", {"status": "stale", "reason": "x"}),
        ("RetractLink", {"reason": "x"}),
    ):
        cases.append((name, "link_id", extra, link))
    for kind in ("restricted", "privileged"):
        post = seeded.extra_ids[f"{kind}_post"]
        for name, extra in (
            ("ReactToPost", {"reaction": "ack"}),
            ("EditPost", {"body": "rewritten"}),
            ("RetractPost", {"reason": "x"}),
        ):
            cases.append((name, "post_id", extra, post))
    for kind in ("restricted", "privileged", "bogus"):
        record = seeded.ids[kind]
        for name, extra in (
            ("UpdateRecord", {"expected_version": 1, "changes": {"title": "x"}}),
            ("VoidRecord", {"expected_version": 1, "reason": "x"}),
            ("TransitionWorkflow", {"expected_version": 1, "transition": "x"}),
        ):
            cases.append((name, "stream_id", extra, record))
    assert len(cases) >= 20
    for name, field, extra, hidden_id in cases:
        results = [
            _answer(client, name, {field: target, **extra}, headers)
            for target in (hidden_id, FAKE_ID)
        ]
        assert results[0].status_code == results[1].status_code, (name, results[0].text[:200])
        assert results[0].status_code == 404, (name, results[0].status_code, results[0].text[:200])
        assert results[0].text.replace(hidden_id, FAKE_ID) == results[1].text, name


def test_repin_a_link_from_a_hidden_post_and_a_taken_post_id_say_nothing_about_the_record(
    harness: Harness, seeded: Seed
) -> None:
    """RepinDocumentLink, AddLink from a hidden post and a post id that is taken (review)."""
    client = harness.client_for(None)
    headers = {"Authorization": f"Bearer {seeded.tokens['bob']}"}
    link, post = seeded.extra_ids["link"], seeded.extra_ids["restricted_post"]
    repin = [
        _answer(client, "RepinDocumentLink", {"link_id": target, "pin": "A"}, headers)
        for target in (link, FAKE_ID)
    ]
    assert [r.status_code for r in repin] == [404, 404], repin[0].text
    assert repin[0].text.replace(link, FAKE_ID) == repin[1].text
    adds = [
        _answer(
            client,
            "AddLink",
            {"from_id": target, "to_id": seeded.ids["open"], "relation": "references"},
            headers,
        )
        for target in (post, FAKE_ID)
    ]
    assert [r.status_code for r in adds] == [404, 404], adds[0].text
    assert adds[0].text.replace(post, FAKE_ID) == adds[1].text
    taken = _answer(
        client, "PostToFeed", {"post_id": seeded.ids["restricted"], "body": "hi"}, headers
    )
    assert (
        taken.status_code == 409 and "found" not in taken.text
    )  # says taken, not what or at what version

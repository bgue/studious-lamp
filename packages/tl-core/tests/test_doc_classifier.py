"""The doc_classifier keeps the enricher contract and meets its floor on the golden set (T06)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest
import yaml
from tl_core.integration.contract import (
    ENRICH_MAX_VALUE_CHARS,
    EnrichmentFile,
    EnrichmentSubject,
    RecordRef,
)
from tl_core.integration.enrichers.doc_classifier import DocClassifier

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests" / "contract"))

from test_integration_contract import check_enricher_contract  # noqa: E402

GOLDEN = json.loads((ROOT / "tests/golden/enrichment/doc_classifier.json").read_text("utf-8"))
STANDARDS = yaml.safe_load(
    (ROOT / "schema/fixtures/standards/co.acme.standards@1.0.0.yaml").read_text("utf-8")
)
#: The floor of FANOUT D6: below this accuracy on ``doc_type`` the evaluation fails.
DOC_TYPE_FLOOR = 0.8


def codes(list_name: str) -> set[str]:
    return {entry["code"] for entry in STANDARDS["code_lists"][list_name]["values"]}


def subject_of(case: dict[str, Any]) -> EnrichmentSubject:
    return EnrichmentSubject(
        record=RecordRef(id=case["id"], key=case["key"], record_type="documents.Document"),
        title=case["title"],
        file=EnrichmentFile(
            file_id=f"file-{case['id']}",
            filename=case["filename"],
            content_type=case["content_type"],
            size=1000,
            sha256="0" * 64,
            page_count=case["page_count"],
            title=case["file_title"],
        ),
    )


def make(
    title: str = "",
    key: str | None = None,
    filename: str | None = None,
    file_title: str | None = None,
) -> EnrichmentSubject:
    file = None
    if filename is not None:
        file = EnrichmentFile(
            file_id="f",
            filename=filename,
            content_type="application/pdf",
            size=1,
            sha256="0" * 64,
            title=file_title,
        )
    return EnrichmentSubject(
        record=RecordRef(id="r1", key=key, record_type="documents.Document"), title=title, file=file
    )


def proposed(subject: EnrichmentSubject) -> dict[str, tuple[Any, float]]:
    result = DocClassifier().enrich(subject)
    return {v.property: (v.value, v.confidence) for v in result.values}


def test_it_passes_the_shared_enricher_contract_checks() -> None:
    check_enricher_contract(DocClassifier(), [subject_of(c) for c in GOLDEN["cases"]])


def test_it_is_a_deterministic_enricher_with_no_model() -> None:
    classifier = DocClassifier()
    assert classifier.name == "doc_classifier"
    assert classifier.model_ref is None
    assert classifier.version


def test_the_golden_set_has_at_least_twenty_cases_and_uses_real_codes() -> None:
    cases = GOLDEN["cases"]
    assert len(cases) >= 20
    assert len({c["id"] for c in cases}) == len(cases)
    for case in cases:
        assert case["doc_type"] is None or case["doc_type"] in codes("DocumentType"), case["id"]
        assert case["discipline"] is None or case["discipline"] in codes("Discipline"), case["id"]


def test_every_value_it_proposes_is_a_code_of_the_companys_lists() -> None:
    for case in GOLDEN["cases"]:
        for prop, (value, confidence) in proposed(subject_of(case)).items():
            assert value in codes({"doc_type": "DocumentType", "discipline": "Discipline"}[prop])
            assert 0.0 <= confidence <= 1.0


def test_accuracy_on_the_golden_set_reaches_the_floor_for_doc_type(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hits = {"doc_type": 0, "discipline": 0}
    for case in GOLDEN["cases"]:
        got = {prop: value for prop, (value, _) in proposed(subject_of(case)).items()}
        for prop in hits:
            hits[prop] += int(got.get(prop) == case[prop])
    total = len(GOLDEN["cases"])
    accuracy = {prop: hit / total for prop, hit in hits.items()}
    (tmp_path / "report.json").write_text(json.dumps({"cases": total, "accuracy": accuracy}))
    with capsys.disabled():
        print(f"\ndoc_classifier accuracy on {total} cases: {accuracy}")
    assert accuracy["doc_type"] >= DOC_TYPE_FLOOR


def test_the_document_number_is_the_surest_evidence() -> None:
    got = proposed(make(title="Something unrelated", key="ISO-1234"))
    assert got["doc_type"] == ("ISO", 0.95)


def test_a_keyword_in_the_title_beats_one_only_in_the_file_name() -> None:
    from_title = proposed(make(title="Pump datasheet", filename="x.pdf"))["doc_type"]
    from_file = proposed(make(title="Revision 2", filename="pump-datasheet.pdf"))["doc_type"]
    assert from_title == ("DS", 0.85)
    assert from_file == ("DS", 0.7)


def test_the_longest_phrase_wins() -> None:
    got = proposed(make(title="Welding procedure specification for carbon steel"))
    assert got["doc_type"][0] == "WPS"
    assert proposed(make(title="Test procedure"))["doc_type"][0] == "PRC"


def test_a_general_drawing_is_never_sure() -> None:
    value, confidence = proposed(make(title="Site drawing"))["doc_type"]
    assert value == "DRW" and confidence <= 0.5


def test_a_keyword_is_a_whole_word() -> None:
    assert "doc_type" not in proposed(make(title="Photo log of the site"))  # not "mto"
    assert "doc_type" not in proposed(
        make(title="Specifications")
    )  # not "spec" nor "specification"
    assert proposed(make(title="P&ID for unit 47"))["doc_type"][0] == "PID"


def test_case_and_punctuation_do_not_matter() -> None:
    assert proposed(make(title="DATA-SHEET, pump"))["doc_type"][0] == "DS"
    assert proposed(make(title="Material Take-Off"))["doc_type"][0] == "MTO"


def test_nothing_matched_is_unsupported_with_no_values() -> None:
    result = DocClassifier().enrich(make(title="Meeting minutes"))
    assert result.status == "unsupported" and result.values == [] and result.problems == []
    assert any("ADR-0008" in note for note in result.notes)


def test_it_ignores_a_subject_with_nothing_to_read() -> None:
    assert not DocClassifier().accepts(make())
    assert DocClassifier().accepts(make(title="x"))
    assert DocClassifier().accepts(make(filename="x.pdf"))


def test_a_hostile_title_is_cheap_and_never_an_error() -> None:
    started = time.monotonic()
    for title in (
        "isometric " * 200_000,
        "a" * 2_000_000,
        "\x00\x01\ud800 datasheet ‮",
        "p&id " * 100_000,
    ):
        result = DocClassifier().enrich(make(title=title, filename="é.pdf"))
        assert result.status in ("ok", "unsupported")
        for value in result.values:
            assert isinstance(value.value, str) and len(value.value) <= ENRICH_MAX_VALUE_CHARS
    assert time.monotonic() - started < 2.0


def test_text_past_the_read_limit_is_not_read() -> None:
    padded = make(title=("word " * 1_000) + "datasheet")
    assert "doc_type" not in proposed(padded)


def test_the_result_names_the_enricher_and_its_version() -> None:
    classifier = DocClassifier()
    result = classifier.enrich(make(title="Loop diagram"))
    assert (result.enricher, result.enricher_version) == (classifier.name, classifier.version)
    assert result.links == []


def test_a_lower_case_number_prefix_counts() -> None:
    assert proposed(make(key="iso-1234"))["doc_type"] == ("ISO", 0.95)


def test_a_number_without_a_hyphen_has_no_prefix() -> None:
    assert "doc_type" not in proposed(make(key="ISO"))
    assert "doc_type" not in proposed(make(key="ISO1234"))


def test_a_number_beats_a_keyword_of_the_title() -> None:
    assert proposed(make(title="Pump datasheet", key="ISO-1234"))["doc_type"][0] == "ISO"


def test_a_record_with_only_a_key_is_read() -> None:
    assert DocClassifier().accepts(make(key="ISO-1"))
    assert proposed(make(key="ISO-1"))["doc_type"][0] == "ISO"


def test_the_title_beats_the_file_whatever_the_file_says() -> None:
    got = proposed(make(title="Pump datasheet", filename="pump-procedure.pdf"))
    assert got["doc_type"] == ("DS", 0.85)


def test_a_tie_goes_to_the_code_first_in_the_table() -> None:
    assert proposed(make(title="Specification datasheet"))["doc_type"][0] == "DS"
    assert proposed(make(title="Datasheet specification"))["doc_type"][0] == "DS"


def test_the_file_extension_is_not_read() -> None:
    assert "doc_type" not in proposed(make(title="Revision 2", filename="report.itr"))
    assert proposed(make(title="Revision 2", filename="itr.pdf"))["doc_type"][0] == "ITR"


def test_the_title_metadata_of_the_file_is_read() -> None:
    got = proposed(make(title="Revision 2", filename="scan.pdf", file_title="Isometric, line 6"))
    assert got["doc_type"] == ("ISO", 0.7)
    assert got["discipline"][0] == "PIP"


def test_only_the_first_discipline_is_proposed() -> None:
    result = DocClassifier().enrich(make(title="Pump list", filename="electrical.pdf"))
    assert [v.property for v in result.values].count("discipline") == 1
    assert {v.property: v.value for v in result.values}["discipline"] == "MEC"


def test_a_keyword_is_the_whole_phrase_not_its_first_word() -> None:
    assert "doc_type" not in proposed(make(title="Material list"))
    assert "doc_type" not in proposed(make(title="Welding record"))
    assert proposed(make(title="Material take off"))["doc_type"][0] == "MTO"

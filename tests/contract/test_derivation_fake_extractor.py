"""The fake extractor of the pipeline tests keeps the extractor contract (P1-I3)."""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_extractor_contract import check_extractor_contract, source_for  # noqa: E402
from tl_core.derivation.testing import FakeExtractor  # noqa: E402

CSV = b"tag,service\n47-FV-1001,Feed valve\n47-FV-1002,\n"


def test_the_fake_extractor_passes_the_shared_contract_checks() -> None:
    check_extractor_contract(
        FakeExtractor(),
        [
            ("index.csv", "text/csv", CSV),
            ("empty.csv", "text/csv", b""),
            ("ragged.csv", "text/csv", b"a,b\n1\n"),
            ("latin.csv", "text/csv", b"a\n\xe9\n"),
            ("scan.pdf", "application/pdf", b"%PDF"),
        ],
    )


def test_the_fake_extractor_reads_rows_and_profiles_columns() -> None:
    result = FakeExtractor().extract(source_for("index.csv", "text/csv", CSV), io.BytesIO(CSV), {})
    assert result.status == "ok" and result.columns == ["tag", "service"]
    assert result.rows[1] == {"tag": "47-FV-1002", "service": None}
    assert [p.non_empty for p in result.profiles] == [2, 1]

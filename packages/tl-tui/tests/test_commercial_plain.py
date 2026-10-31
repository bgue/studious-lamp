"""The Commercial register, its panel, the RFI log, the evidence trail and the commercial details
in plain words, and the technical mode that gives the internal form back (P1-UX-T05)."""

from __future__ import annotations

from fakes import FakeClient
from fakes_correspondence import seed_domains
from tl_tui import commercial_text as ct
from tl_tui import evidence_text as et
from tl_tui import rfi_text as rt
from tl_tui.details import details_for
from tl_tui.display import DisplayMode, Labels, find_technical


def seeded() -> FakeClient:
    client = FakeClient()
    seed_domains(client)
    return client


def labels() -> Labels:
    """The labels a screen loads for the seeded project, written out by hand."""
    return Labels(
        domains={"commercial": "Commercial", "technical": "Technical"},
        subtypes={
            ("commercial", "early_warning"): "Early warning",
            ("commercial", "change_notice"): "Change notice",
            ("technical", "rfi"): "Request for information",
        },
        code_labels={"confidentiality": {"restricted": "Restricted", "internal": "Internal"}},
        type_titles={
            "correspondence.CommercialItem": "Commercial item",
            "correspondence.TechnicalItem": "Technical item",
        },
    )


def test_the_register_has_eleven_columns_and_no_status_column() -> None:
    assert len(ct.COMMERCIAL_COLUMNS) == 11
    assert "Status" not in ct.COMMERCIAL_COLUMNS
    for line in seeded().list_commercial("P123").lines:
        assert len(ct.commercial_cells(line)) == 11
        assert len(ct.commercial_cells(line, labels(), technical=False)) == 11


def test_plain_commercial_cells_and_panel_use_words_and_find_technical_is_empty() -> None:
    client = seeded()
    lab = labels()
    warning_line = client.list_commercial("P123").lines[0]
    cells = ct.commercial_cells(warning_line, lab, technical=False)
    assert cells[1] == "Early warning: routing change"
    assert cells[2] == "Awaiting assessment"
    assert cells[3] == "Early warning"
    assert cells[7] == "LATE"
    panel = ct.commercial_lines(client.get_commercial("P123", "P123-EW-0001"), lab)
    assert panel[0] == "P123-EW-0001 · Early warning: routing change"
    assert panel[1] == "Awaiting assessment"
    assert "Kind             Early warning" in panel
    assert "Confidentiality  Restricted" in panel
    rfi_line = client.list_rfis("P123").lines[1]
    rfi_row = rt.rfi_cells(rfi_line, lab, technical=False)
    rfi_panel = rt.rfi_lines(client.get_rfi("P123", "P123-RFI-0002"), lab)
    trail = client.get_evidence_trail("P123", "P123-EW-0001")
    evidence_cells = [et.node_cells(n, lab, technical=False) for n in trail.nodes]
    evidence_panel = [line for n in trail.nodes for line in et.node_lines(n, lab)]
    # a record with no number shows its place, never its record id
    keyless = trail.nodes[1].model_copy(update={"key": None})
    assert et.node_cells(keyless, lab, technical=False)[0] == "  (no number)"
    text = "\n".join(
        [
            *cells,
            *panel,
            *rfi_row,
            *rfi_panel,
            *(c for row in evidence_cells for c in row),
            *evidence_panel,
        ]
    )
    assert "early_warning" not in text
    assert "P123-EW-0001-C" not in text
    assert find_technical(text, lab) == []


def test_technical_flag_restores_the_clock_key_and_the_raw_kind() -> None:
    client = seeded()
    lab = labels()
    clock = client.get_rfi("P123", "P123-RFI-0002").clocks[0]
    warning = client.get_commercial("P123", "P123-EW-0001").model_copy(update={"clocks": [clock]})
    lines = ct.commercial_lines(warning, lab, technical=True)
    assert lines[0] == "P123-EW-0001 · Early warning: routing change"
    assert lines[1] == "Awaiting assessment"
    assert any(x.startswith("Record id") and x.endswith("ID-P123-EW-0001") for x in lines)
    assert any("P123-RFI-0002-C01 · calendar " in x for x in lines)
    warning_line = client.list_commercial("P123").lines[0]
    assert ct.commercial_cells(warning_line)[2:4] == ("Awaiting assessment", "early_warning")
    assert ct.commercial_cells(warning_line, lab, technical=False)[2:4] == (
        "Awaiting assessment",
        "Early warning",
    )
    rfi_line = client.list_rfis("P123").lines[1]
    assert rt.rfi_cells(rfi_line)[2:4] == ("Awaiting response", "rfi")
    assert rt.rfi_cells(rfi_line, lab, technical=False)[2:4] == ("Awaiting response", "RFI")
    panel = rt.rfi_lines(client.get_rfi("P123", "P123-RFI-0002"), lab, technical=True)
    assert panel[0] == "P123-RFI-0002 · Cable tray height"
    assert panel[1].startswith("Awaiting response")
    assert any(x.startswith("Record id") and x.endswith("ID-P123-RFI-0002") for x in panel)


def test_the_commercial_details_rows_are_labelled() -> None:
    client = seeded()
    lab = labels()
    record = {"type": "correspondence.CommercialItem", "key": "P123-EW-0001"}
    plain = details_for(client, "P123", record, lab, DisplayMode())
    rows = {row.label: row.value for row in plain}
    # the number, subject and state are the heading of the page, not rows; the type is the Kind
    assert not {"Type", "Number", "Subject", "State"} & set(rows)
    assert rows["Kind"] == "Early warning"
    assert rows["Confidentiality"] == "Restricted"
    assert rows["Estimated"] == "12500.00 USD"
    assert rows["Schedule impact"] == "3 days"
    assert rows["Cost codes"] == "2.3.1=12500.00"
    assert any(row.section == "Basis" and row.value == "Clause 20.1" for row in plain)
    assert rows["Escalated from"] == "P123-RFI-0001"
    # an early warning not yet assessed shows the fixed Assessment section with dashes
    assert [row.value for row in plain if row.section == "Assessment"] == ["—", "—", "—"]
    assert not any(row.technical for row in plain)
    mode = DisplayMode()
    mode.technical = True
    technical = details_for(client, "P123", record, lab, mode)
    assert {"Key", "Version", "Scope", "Schema hash"} <= {row.label for row in technical}
    assert any(row.technical for row in technical)

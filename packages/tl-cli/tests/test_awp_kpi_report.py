"""P2-I5-T09: `tl awp report kpi_ppc` and `kpi_constraint_free` print one KPI row each."""

from __future__ import annotations

from pathlib import Path

from test_cli_awp import Cli, seed_copy

COLUMNS = "name,value,numerator,denominator,detail"


def test_each_kpi_report_prints_one_row_with_the_named_columns(tmp_path: Path) -> None:
    cli = Cli(seed_copy(tmp_path), tmp_path)
    for name in ("kpi_ppc", "kpi_constraint_free"):
        lines = cli.ok("report", name)
        assert len(lines) == 1, lines
        cells = lines[0].split("  ")
        assert len(cells) == 5, lines
        assert cells[0] == name


def test_the_csv_form_has_the_header_line_then_one_row(tmp_path: Path) -> None:
    cli = Cli(seed_copy(tmp_path), tmp_path)
    for name in ("kpi_ppc", "kpi_constraint_free"):
        lines = cli.ok("report", name, "--csv")
        assert lines[0] == COLUMNS
        assert len(lines) == 2, lines
        assert lines[1].startswith(f"{name},")


def test_an_unknown_name_is_an_error_with_exit_1_and_no_traceback(tmp_path: Path) -> None:
    cli = Cli(seed_copy(tmp_path), tmp_path)
    result = cli.project("report", "kpi_nope")
    assert result.exit_code == 1
    assert result.stderr.startswith("error: report must be one of ")
    assert "kpi_ppc" in result.stderr and "kpi_constraint_free" in result.stderr
    assert "Traceback" not in result.output

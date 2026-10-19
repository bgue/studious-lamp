"""Helpers of the tl-xer tests: a synthetic file as text, and edits to it (P1-I4-T03)."""

from __future__ import annotations

from tl_xer.synth import make_xer, week_pair


def first_text() -> str:
    """The first demo file as text (it is Windows-1252 on the wire)."""
    return make_xer(week_pair()[0]).decode("cp1252")


def second_text() -> str:
    return make_xer(week_pair()[1]).decode("cp1252")


def encode(text: str, encoding: str = "cp1252") -> bytes:
    return text.encode(encoding)


def replace_once(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, f"{old!r} occurs {text.count(old)} times"
    return text.replace(old, new)


def drop_table(text: str, name: str) -> str:
    """``text`` without the ``%T name`` section."""
    lines = text.split("\r\n")
    out: list[str] = []
    skipping = False
    for line in lines:
        if line.startswith("%T\t"):
            skipping = line == f"%T\t{name}"
        if line == "%E":
            skipping = False
        if not skipping:
            out.append(line)
    return "\r\n".join(out)


def drop_column(text: str, table: str, column: str) -> str:
    """``text`` without ``column`` of ``table`` (header and every row)."""
    lines = text.split("\r\n")
    out: list[str] = []
    current = ""
    position = -1
    for line in lines:
        fields = line.split("\t")
        if fields[0] == "%T":
            current = fields[1]
            position = -1
        elif fields[0] == "%F" and current == table:
            position = fields.index(column)
            del fields[position]
            line = "\t".join(fields)
        elif fields[0] == "%R" and current == table and position >= 0:
            if position < len(fields):
                del fields[position]
            line = "\t".join(fields)
        out.append(line)
    return "\r\n".join(out)


def set_cell(text: str, table: str, row: int, column: str, value: str) -> str:
    """``text`` with ``value`` in data row ``row`` (1-based) of ``table``, ``column``."""
    lines = text.split("\r\n")
    out: list[str] = []
    current = ""
    names: list[str] = []
    seen = 0
    for line in lines:
        fields = line.split("\t")
        if fields[0] == "%T":
            current, seen = fields[1], 0
        elif fields[0] == "%F" and current == table:
            names = fields[1:]
        elif fields[0] == "%R" and current == table:
            seen += 1
            if seen == row:
                fields[1 + names.index(column)] = value
                line = "\t".join(fields)
        out.append(line)
    return "\r\n".join(out)


def codes(problems: list[dict[str, object]]) -> list[object]:
    return [p["code"] for p in problems]


def big_text(
    activities: int,
    *,
    wide_rows: int = 0,
    wide_columns: int = 200,
    short_cells: bool = False,
    cell: str | None = None,
) -> bytes:
    """A valid file of ``activities`` activities (two relationships each) and an extra wide table.

    ``wide_rows`` rows of ``wide_columns`` columns go into a table the snapshot is not typed from
    (bronze only), to reach the memory limit cheaply; ``cell`` fills every cell of them with that
    text (``short_cells`` is the cell ``1``).
    """
    out = ["ERMHDR\t20.12\t2026-10-05\tProject\tu\tU\tDB\tPM\tUSD"]

    def table(name: str, cols: list[str], rows: object) -> None:
        out.append(f"%T\t{name}")
        out.append("\t".join(["%F", *cols]))
        out.extend("\t".join(["%R", *r]) for r in rows)  # type: ignore[attr-defined]

    table(
        "PROJECT",
        ["proj_id", "proj_short_name", "clndr_id", "last_recalc_date"],
        [["1", "BIG", "1", "2026-10-05 08:00"]],
    )
    table(
        "CALENDAR",
        ["clndr_id", "clndr_name", "day_hr_cnt"],
        [["1", "Standard", "8"]],
    )
    table(
        "PROJWBS",
        ["wbs_id", "proj_id", "wbs_short_name", "wbs_name", "parent_wbs_id"],
        [["100", "1", "BIG", "Big", ""]]
        + [[str(101 + i), "1", f"W{i}", f"Area {i}", "100"] for i in range(50)],
    )
    task_columns = [
        "task_id", "proj_id", "wbs_id", "clndr_id", "task_type", "status_code", "task_code",
        "task_name", "total_float_hr_cnt", "target_drtn_hr_cnt", "remain_drtn_hr_cnt",
        "early_start_date", "early_end_date", "late_start_date", "late_end_date",
        "act_start_date", "act_end_date",
    ]  # fmt: skip
    table(
        "TASK",
        task_columns,
        (
            [
                str(1000 + i),
                "1",
                str(101 + i % 50),
                "1",
                "TT_Task",
                "TK_NotStart",
                f"A{i:06d}",
                f"Activity {i} with a reasonably long descriptive name",
                "40",
                "80",
                "80",
                "2026-10-12 08:00",
                "2026-10-23 16:00",
                "2026-10-19 08:00",
                "2026-10-30 16:00",
                "",
                "",
            ]  # fmt: skip
            for i in range(activities)
        ),
    )
    predecessors = [
        [str(i * 2 + k), str(1000 + i), str(1000 + i - k), "1", "1", "PR_FS", "0"]
        for i in range(2, activities)
        for k in (1, 2)
    ]
    table(
        "TASKPRED",
        [
            "task_pred_id",
            "task_id",
            "pred_task_id",
            "proj_id",
            "pred_proj_id",
            "pred_type",
            "lag_hr_cnt",
        ],
        predecessors,
    )
    if wide_rows:
        table(
            "WIDE",
            [f"c{i}" for i in range(wide_columns)],
            (
                [cell] * wide_columns
                if cell is not None
                else ["1"] * wide_columns
                if short_cells
                else [f"v{r}x{c}" for c in range(wide_columns)]
                for r in range(wide_rows)
            ),
        )
    out.append("%E")
    return ("\r\n".join(out) + "\r\n").encode("cp1252")


def add_row(text: str, table: str, fields: list[str]) -> str:
    """``text`` with one more data row (fields in column order) at the end of ``table``."""
    lines = text.split("\r\n")
    out: list[str] = []
    inside = False
    for line in lines:
        if inside and (line.startswith("%T\t") or line == "%E"):
            out.append("\t".join(["%R", *fields]))
            inside = False
        out.append(line)
        if line == f"%T\t{table}":
            inside = True
    return "\r\n".join(out)


def max_counts_text(
    *,
    name_char: str = "n",
    code_name_len: int = 0,
    udf_pad: int = 0,
    task_pad: int = 330,
    activities: int = 60_000,
    relationships: int = 200_000,
    codes: int = 300_000,
    udfs: int = 300_000,
) -> bytes:
    """A valid file at the typed maximum (60 000 activities, 200 000 relationships, 300 000 codes,
    300 000 user fields; about 49 MB). ``name_char`` repeated ``code_name_len`` times is the name
    of each of 50 activity codes (a code name is copied into every row that uses it); a
    ``task_pad`` characters pad each activity name so the file reaches the byte limit; ``udf_pad``
    pads the user fields. UTF-8 when the text needs it."""
    out = ["ERMHDR\t20.12\t2026-10-05\tProject\tu\tU\tDB\tPM\tUSD"]

    def table(name: str, cols: list[str], rows: object) -> None:
        out.append(f"%T\t{name}")
        out.append("\t".join(["%F", *cols]))
        out.extend("\t".join(["%R", *r]) for r in rows)  # type: ignore[attr-defined]

    table(
        "PROJECT",
        ["proj_id", "proj_short_name", "clndr_id", "last_recalc_date"],
        [["1", "BIG", "1", "2026-10-05 08:00"]],
    )
    table("CALENDAR", ["clndr_id", "clndr_name", "day_hr_cnt"], [["1", "Standard", "8"]])
    table(
        "PROJWBS",
        ["wbs_id", "proj_id", "wbs_short_name", "wbs_name", "parent_wbs_id"],
        [["100", "1", "BIG", "Big", ""]]
        + [[str(101 + i), "1", f"W{i}", f"Area {i}", "100"] for i in range(50)],
    )
    task_columns = [
        "task_id", "proj_id", "wbs_id", "clndr_id", "task_type", "status_code", "task_code",
        "task_name", "total_float_hr_cnt", "target_drtn_hr_cnt", "remain_drtn_hr_cnt",
        "early_start_date", "early_end_date", "late_start_date", "late_end_date",
        "act_start_date", "act_end_date",
    ]  # fmt: skip
    table(
        "TASK",
        task_columns,
        (
            [
                str(1000 + i),
                "1",
                str(101 + i % 50),
                "1",
                "TT_Task",
                "TK_NotStart",
                f"A{i:06d}",
                f"Activity {i} with a reasonably long descriptive name" + "x" * task_pad,
                "40",
                "80",
                "80",
                "2026-10-12 08:00",
                "2026-10-23 16:00",
                "2026-10-19 08:00",
                "2026-10-30 16:00",
                "",
                "",
            ]  # fmt: skip
            for i in range(activities)
        ),
    )
    predecessors: list[list[str]] = []
    for i in range(activities):
        for back in (1, 2, 3, 4):
            if len(predecessors) >= relationships or i - back < 0:
                continue
            predecessors.append(
                [
                    str(len(predecessors) + 1),
                    str(1000 + i),
                    str(1000 + i - back),
                    "1",
                    "1",
                    "PR_FS",
                    "0",
                ]
            )
    table(
        "TASKPRED",
        [
            "task_pred_id", "task_id", "pred_task_id", "proj_id", "pred_proj_id", "pred_type",
            "lag_hr_cnt",
        ],
        predecessors,
    )  # fmt: skip
    if codes:
        table("ACTVTYPE", ["actv_code_type_id", "actv_code_type", "proj_id"], [["1", "Area", "1"]])
        table(
            "ACTVCODE",
            ["actv_code_id", "actv_code_type_id", "short_name", "actv_code_name"],
            [
                [str(11 + c), "1", f"C{c}", (name_char * code_name_len) or f"name {c}"]
                for c in range(50)
            ],
        )
        table(
            "TASKACTV",
            ["task_id", "actv_code_type_id", "actv_code_id", "proj_id"],
            ([str(1000 + n % activities), "1", str(11 + n % 50), "1"] for n in range(codes)),
        )
    if udfs:
        table(
            "UDFTYPE",
            ["udf_type_id", "table_name", "udf_type_name", "udf_type_label", "logical_data_type"],
            [["501", "TASK", "user_field_1", "Contractor reference", "FT_TEXT"]],
        )
        table(
            "UDFVALUE",
            ["udf_type_id", "fk_id", "proj_id", "udf_text"],
            (
                ["501", str(1000 + n % activities), "1", f"v{n}" + "u" * udf_pad]
                for n in range(udfs)
            ),
        )
    out.append("%E")
    return ("\r\n".join(out) + "\r\n").encode("utf-8")

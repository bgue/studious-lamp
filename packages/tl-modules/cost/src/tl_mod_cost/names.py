"""Names the cost module shares: record types, event types, tables, measures, relations.

Plain constants, so a projector, a handler, a CLI command and a test all spell them the same way.
"""

from __future__ import annotations

from typing import Final

COST_CODE: Final = "cost.CostCode"
COST_SNAPSHOT: Final = "cost.CostSnapshot"
RECORD_TYPES: Final = frozenset({COST_CODE, COST_SNAPSHOT})

COST_CODE_TABLE: Final = "cur_cost_costcode"
COST_SNAPSHOT_TABLE: Final = "cur_cost_cost_snapshot"
SNAPSHOT_VALUE_TABLE: Final = "cur_cost_snapshot_value"
COST_CODE_VIEW: Final = "v_cost_cost_code"
COST_SNAPSHOT_VIEW: Final = "v_cost_cost_snapshot"

CODE_DEFINED: Final = "CostCode.Defined"
CODE_REVISED: Final = "CostCode.Revised"
MEASURES_RECORDED: Final = "CostCode.MeasuresRecorded"
SNAPSHOT_DEFINED: Final = "CostSnapshot.Defined"

#: The measure matrix: {hours, quantity, amount} x {budget, actual, earned, ftc, eac}.
UNITS: Final = ("hours", "quantity", "amount")
MEASURES: Final = ("budget", "actual", "earned", "ftc", "eac")
MEASURE_COLUMNS: Final = tuple(f"{unit}_{measure}" for unit in UNITS for measure in MEASURES)

#: Relation of the link from any record to the cost code it is costed to (brief 7.1, M11). The
#: vocabulary of links is the thirteen of brief 7.1: the cost code is told by the type of the
#: record the link points at (``cost.CostCode``).
COST_RELATION: Final = "references"

"""The gold pass: SQL models over silver and bronze, one table each (brief 28.2; P2-I6).

Each model is a file ``models/<name>.sql`` holding one ``SELECT``. :func:`build_gold_marts`
replaces every model's table whole, in :data:`GOLD_MODELS` order (a later model may read an earlier
one), inside the open transaction of the sync that calls it, so a mart never disagrees with the
tables it came from. A model whose ``needs`` are not all in the lake leaves no table (a stale one
is dropped): the table exists, possibly empty, whenever its needs do.

A model reads only the lake tables it names in ``needs`` and, by the lake's rule, holds nothing
about a record the lowest reader may not read: silver and bronze hold none, so a model that only
reads them cannot.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files

from tl_lake.duck import Duck, lake_tables, table_ref

RECORD_TABLE = "cur_core_record"


@dataclass(frozen=True)
class GoldModel:
    """A gold table: its name (``mart_...``, also the SQL file's) and the lake tables it needs."""

    name: str
    needs: tuple[str, ...]
    #: Columns of the model that hold a record id. The runner keeps a row only when each is NULL or
    #: the id is in the lake's ``cur_core_record`` (silver holds readable records only), on every
    #: sync: a record hidden after its events were copied leaves the mart without a rebuild.
    record_columns: tuple[str, ...] = ()


GOLD_MODELS: tuple[GoldModel, ...] = (
    GoldModel("mart_iwp_readiness_history", ("events", RECORD_TABLE), record_columns=("iwp_id",)),
    GoldModel("mart_materials", ("cur_materials_movement", "cur_materials_stock")),
    GoldModel(
        "mart_schedule_vs_readiness", ("mart_schedule_history", "mart_iwp_readiness_history")
    ),
)


def model_sql(name: str) -> str:
    """The text of ``models/<name>.sql``: one ``SELECT``, no trailing ``;``."""
    text = files("tl_lake").joinpath("models", f"{name}.sql").read_text(encoding="utf-8")
    return text.strip().rstrip(";").rstrip()


def _guarded_sql(model: GoldModel) -> str:
    """The model's SELECT, restricted to rows whose record ids (``record_columns``) are readable."""
    sql = model_sql(model.name)
    if not model.record_columns:
        return sql
    keep = " AND ".join(
        f'(model."{c}" IS NULL OR model."{c}" IN (SELECT id FROM {table_ref(RECORD_TABLE)}))'
        for c in model.record_columns
    )
    return f"SELECT * FROM ({sql}) AS model WHERE {keep}"


def build_gold_marts(con: Duck) -> None:
    """Replace every gold table from its model; skip (and drop) a model whose needs are missing."""
    for model in GOLD_MODELS:
        con.execute(f"DROP TABLE IF EXISTS {table_ref(model.name)}")
        if set(model.needs) <= set(lake_tables(con)):
            con.execute(f"CREATE TABLE {table_ref(model.name)} AS {_guarded_sql(model)}")

"""Write generated DataFrames to a single .sql dump file.

Supports two dialects: PostgreSQL (``postgres``) and Microsoft SQL Server
(``mssql``). Emits a header comment, transaction wrapper, all ``CREATE TABLE``
DDL in topological order, then batched ``INSERT INTO ... VALUES`` statements,
ending with ``COMMIT``.

Constraints embedded in DDL:
- ``PRIMARY KEY`` from ``primary_key: true`` in the schema YAML
- ``UNIQUE`` from ``unique: true`` in the schema YAML
- ``REFERENCES parent(col)`` for FK columns (no ON DELETE / ON UPDATE)

Inserts are batched at 1000 rows per ``VALUES`` clause to stay within MSSQL's
hard limit; the same chunk-size keeps Postgres dumps diffable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

MAX_BATCH_ROWS = 1000


@dataclass(frozen=True)
class Dialect:
    name: str
    quote_ident: Callable[[str], str]
    string_literal: Callable[[str], str]
    type_map: Dict[str, str]
    tx_begin: str
    tx_commit: str


def _pg_quote_ident(s: str) -> str:
    return '"' + s.replace('"', '""') + '"'


def _mssql_quote_ident(s: str) -> str:
    return "[" + s.replace("]", "]]") + "]"


def _pg_string_literal(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _mssql_string_literal(s: str) -> str:
    return "N'" + s.replace("'", "''") + "'"


POSTGRES = Dialect(
    name="postgres",
    quote_ident=_pg_quote_ident,
    string_literal=_pg_string_literal,
    type_map={
        "int": "BIGINT",
        "float": "DOUBLE PRECISION",
        "bool": "BOOLEAN",
        "str": "TEXT",
        "datetime": "TIMESTAMP",
    },
    tx_begin="BEGIN;",
    tx_commit="COMMIT;",
)

MSSQL = Dialect(
    name="mssql",
    quote_ident=_mssql_quote_ident,
    string_literal=_mssql_string_literal,
    type_map={
        "int": "BIGINT",
        "float": "FLOAT",
        "bool": "BIT",
        "str": "NVARCHAR(MAX)",
        "datetime": "DATETIME2",
    },
    tx_begin="BEGIN TRANSACTION;",
    tx_commit="COMMIT;",
)

DIALECTS: Dict[str, Dialect] = {"postgres": POSTGRES, "mssql": MSSQL}


def _canonical_type(dtype) -> str:
    s = str(dtype).lower()
    if "datetime" in s:
        return "datetime"
    if "bool" in s:
        return "bool"
    if "int" in s:
        return "int"
    if "float" in s:
        return "float"
    return "str"


def _create_table_sql(
    d: Dialect,
    table: str,
    df: pd.DataFrame,
    col_specs: List[Dict[str, Any]],
) -> str:
    by_name = {c["name"]: c for c in col_specs}
    lines = []
    for col in df.columns:
        spec = by_name.get(col, {})
        sql_type = d.type_map[_canonical_type(df[col].dtype)]
        suffix = []
        if spec.get("primary_key"):
            suffix.append("PRIMARY KEY")
        if spec.get("unique"):
            suffix.append("UNIQUE")
        if spec.get("provider") == "fk" and isinstance(spec.get("references"), str):
            parent_table, _, parent_col = spec["references"].partition(".")
            suffix.append(
                f"REFERENCES {d.quote_ident(parent_table)}({d.quote_ident(parent_col)})"
            )
        tail = " " + " ".join(suffix) if suffix else ""
        lines.append(f"  {d.quote_ident(col)} {sql_type}{tail}")
    return f"CREATE TABLE {d.quote_ident(table)} (\n" + ",\n".join(lines) + "\n);"


def _format_value(d: Dialect, v: Any) -> str:
    # Order matters: bool before int (bool is an int subclass);
    # datetime before date (datetime is a date subclass).
    if v is None:
        return "NULL"
    if isinstance(v, float) and math.isnan(v):
        return "NULL"
    try:
        if pd.isna(v):
            return "NULL"
    except (TypeError, ValueError):
        pass
    if isinstance(v, (bool, np.bool_)):
        return "1" if bool(v) else "0"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        return repr(float(v))
    if isinstance(v, datetime):
        return d.string_literal(v.isoformat(sep=" "))
    if isinstance(v, date):
        return d.string_literal(v.isoformat())
    return d.string_literal(str(v))


def _chunked(iterable: Iterable, size: int) -> Iterable[List]:
    chunk: List = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _insert_statements(d: Dialect, table: str, df: pd.DataFrame) -> Iterable[str]:
    if df.empty:
        return
    cols_sql = ", ".join(d.quote_ident(c) for c in df.columns)
    header = f"INSERT INTO {d.quote_ident(table)} ({cols_sql}) VALUES"
    for batch in _chunked(df.itertuples(index=False, name=None), MAX_BATCH_ROWS):
        rows_sql = ",\n  ".join(
            "(" + ", ".join(_format_value(d, v) for v in row) + ")" for row in batch
        )
        yield f"{header}\n  {rows_sql};"


def write(
    tables: Dict[str, pd.DataFrame],
    topo_order: List[str],
    output_path: str,
    dialect: str,
    schema_tables: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Write a single .sql file with CREATE + INSERT statements."""
    if dialect not in DIALECTS:
        raise ValueError(
            f"Unknown dialect: {dialect!r}; expected one of {sorted(DIALECTS)}"
        )
    d = DIALECTS[dialect]
    cols_by_table: Dict[str, List[Dict[str, Any]]] = {
        t["name"]: t["columns"] for t in (schema_tables or [])
    }

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"-- syntherklaas SQL export — dialect: {d.name}\n\n")
        f.write(d.tx_begin + "\n\n")
        for table in topo_order:
            df = tables[table]
            col_specs = cols_by_table.get(table, [{"name": c} for c in df.columns])
            f.write(_create_table_sql(d, table, df, col_specs) + "\n\n")
        for table in topo_order:
            for stmt in _insert_statements(d, table, tables[table]):
                f.write(stmt + "\n\n")
        f.write(d.tx_commit + "\n")

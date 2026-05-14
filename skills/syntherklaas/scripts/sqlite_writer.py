"""Write generated DataFrames to a SQLite DB.

The generator emits DataFrames with IDs already assigned and FK columns already
pointing to the correct parent IDs, so this writer is simple: create the table
schema from pandas dtypes, then bulk-insert. Datetime values are serialized as
ISO 8601 strings; numpy scalar types are converted to Python natives.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Dict, List

import numpy as np
import pandas as pd


def _pandas_dtype_to_sqlite(dtype) -> str:
    s = str(dtype).lower()
    if "datetime" in s:
        return "TEXT"
    if "int" in s or "bool" in s:
        return "INTEGER"
    if "float" in s:
        return "REAL"
    return "TEXT"


def _create_table(conn: sqlite3.Connection, table: str, df: pd.DataFrame, pk: str = "id") -> None:
    parts = []
    for col in df.columns:
        sql_type = _pandas_dtype_to_sqlite(df[col].dtype)
        if col == pk:
            parts.append(f'"{col}" {sql_type} PRIMARY KEY')
        else:
            parts.append(f'"{col}" {sql_type}')
    conn.execute(f'CREATE TABLE "{table}" ({", ".join(parts)})')


def _serialize(v):
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    if isinstance(v, np.bool_):
        return bool(v)
    return v


def _insert_rows(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    if df.empty:
        return
    cols = list(df.columns)
    quoted = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(["?"] * len(cols))
    sql = f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})'
    rows = [
        tuple(None if pd.isna(v) else _serialize(v) for v in row)
        for row in df.itertuples(index=False, name=None)
    ]
    conn.executemany(sql, rows)


def write(
    tables: Dict[str, pd.DataFrame],
    topo_order: List[str],
    db_path: str,
    pk_column: str = "id",
) -> None:
    """Create tables and insert rows in topological order."""
    with sqlite3.connect(db_path) as conn:
        for table in topo_order:
            df = tables[table]
            _create_table(conn, table, df, pk_column)
            _insert_rows(conn, table, df)
        conn.commit()

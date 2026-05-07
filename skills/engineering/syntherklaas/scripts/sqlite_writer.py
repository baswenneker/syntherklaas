"""Step 5: write sampled+anonymized DataFrames to SQLite.

Per table in topological order:
1. Validate schema if the table already exists in the DB; fail-fast on mismatch.
2. Otherwise create the table from pandas dtypes.
3. Compute ``MAX(id)`` and assign output IDs starting at ``MAX+1``.
4. Build a per-table ``id_map`` and rewrite FK columns to point at the new IDs.
5. Bulk insert via ``executemany`` (NaN → NULL).
"""

from __future__ import annotations

import sqlite3
from typing import Dict, List

import pandas as pd

from fk_resolver import FksByTable


class SchemaMismatchError(Exception):
    """Raised when input columns don't match an existing DB table's schema."""


IdMap = Dict[str, Dict[object, int]]


def _pandas_dtype_to_sqlite(dtype) -> str:
    s = str(dtype).lower()
    if "int" in s or "bool" in s:
        return "INTEGER"
    if "float" in s:
        return "REAL"
    return "TEXT"


def _create_table(conn: sqlite3.Connection, table: str, df: pd.DataFrame, pk: str) -> None:
    parts = []
    for col in df.columns:
        sql_type = _pandas_dtype_to_sqlite(df[col].dtype)
        if col == pk:
            parts.append(f'"{col}" {sql_type} PRIMARY KEY')
        else:
            parts.append(f'"{col}" {sql_type}')
    conn.execute(f'CREATE TABLE "{table}" ({", ".join(parts)})')


def _validate_schema(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    db_cols = {row[1] for row in rows}
    input_cols = set(df.columns)
    if db_cols != input_cols:
        missing = input_cols - db_cols
        extra = db_cols - input_cols
        raise SchemaMismatchError(
            f"Schema mismatch on '{table}': "
            f"in input but not DB={sorted(missing)}, in DB but not input={sorted(extra)}"
        )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cur.fetchone() is not None


def _max_id(conn: sqlite3.Connection, table: str, pk: str) -> int:
    cur = conn.execute(f'SELECT MAX("{pk}") FROM "{table}"')
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _insert_rows(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    if df.empty:
        return
    cols = list(df.columns)
    quoted = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(["?"] * len(cols))
    sql = f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})'
    rows = [
        tuple(None if pd.isna(v) else v for v in row)
        for row in df.itertuples(index=False, name=None)
    ]
    conn.executemany(sql, rows)


def write(
    sampled: Dict[str, pd.DataFrame],
    fks: FksByTable,
    topo_order: List[str],
    db_path: str,
    pk_column: str = "id",
) -> IdMap:
    """Write sampled tables to SQLite with ID-offset and FK rewriting."""
    id_map: IdMap = {}

    with sqlite3.connect(db_path) as conn:
        for table in topo_order:
            df = sampled[table].copy()

            if _table_exists(conn, table):
                _validate_schema(conn, table, df)
            else:
                _create_table(conn, table, df, pk_column)

            if pk_column in df.columns:
                start = _max_id(conn, table, pk_column) if _table_exists(conn, table) else 0
                input_ids = df[pk_column].tolist()
                output_ids = list(range(start + 1, start + 1 + len(df)))
                id_map[table] = dict(zip(input_ids, output_ids))
                df[pk_column] = output_ids
            else:
                id_map[table] = {}

            for fk in fks.get(table, []):
                parent_map = id_map.get(fk.references_table)
                if not parent_map:
                    continue
                df[fk.column] = df[fk.column].map(parent_map).combine_first(df[fk.column])

            _insert_rows(conn, table, df)

        conn.commit()

    return id_map


def format_report(id_map: IdMap) -> str:
    lines = ["SQLite write:"]
    for table in sorted(id_map):
        bucket = id_map[table]
        if not bucket:
            lines.append(f"  {table}: 0 rows inserted")
            continue
        ids = list(bucket.values())
        lines.append(
            f"  {table}: {len(ids)} rows inserted (IDs {min(ids)}..{max(ids)})"
        )
    return "\n".join(lines)

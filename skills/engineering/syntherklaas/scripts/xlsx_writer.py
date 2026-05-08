"""Step 5 (alternate): write sampled+anonymized DataFrames to a multi-sheet .xlsx.

XLSX output is alleen-nieuw — append mode is not supported. Per table in
topological order:

1. Validate the output path does not already exist.
2. Validate every table name fits Excel's 31-char sheet-name limit.
3. Assign output IDs starting at 1 and build a per-table ``id_map``.
4. Rewrite FK columns to point at the new IDs (identical logic to sqlite_writer).
5. Write each table as a sheet with ``pandas.ExcelWriter`` (openpyxl backend),
   with the header row frozen.
"""

from __future__ import annotations

import os
from typing import Dict, List

import pandas as pd

from fk_resolver import FksByTable

EXCEL_SHEET_NAME_MAX = 31


class OutputExistsError(Exception):
    """Raised when the target .xlsx path already exists."""


class TableNameTooLongError(Exception):
    """Raised when a table name exceeds Excel's 31-char sheet-name limit."""


IdMap = Dict[str, Dict[object, int]]


def _validate_table_names(topo_order: List[str]) -> None:
    too_long = [t for t in topo_order if len(t) > EXCEL_SHEET_NAME_MAX]
    if too_long:
        raise TableNameTooLongError(
            f"Table name(s) exceed Excel's {EXCEL_SHEET_NAME_MAX}-char "
            f"sheet-name limit: {too_long}"
        )


def write(
    sampled: Dict[str, pd.DataFrame],
    fks: FksByTable,
    topo_order: List[str],
    output_path: str,
    pk_column: str = "id",
) -> IdMap:
    """Write sampled tables to a multi-sheet .xlsx with ID-offset and FK rewriting."""
    if os.path.exists(output_path):
        raise OutputExistsError(f"Output xlsx already exists: {output_path}")

    _validate_table_names(topo_order)

    id_map: IdMap = {}
    rewritten: Dict[str, pd.DataFrame] = {}

    for table in topo_order:
        df = sampled[table].copy()

        if pk_column in df.columns:
            input_ids = df[pk_column].tolist()
            output_ids = list(range(1, 1 + len(df)))
            id_map[table] = dict(zip(input_ids, output_ids))
            df[pk_column] = output_ids
        else:
            id_map[table] = {}

        for fk in fks.get(table, []):
            parent_map = id_map.get(fk.references_table)
            if not parent_map:
                continue
            df[fk.column] = df[fk.column].map(parent_map).combine_first(df[fk.column])

        rewritten[table] = df

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for table in topo_order:
            rewritten[table].to_excel(writer, sheet_name=table, index=False)
            writer.sheets[table].freeze_panes = "A2"

    return id_map


def format_report(id_map: IdMap) -> str:
    lines = ["XLSX write:"]
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

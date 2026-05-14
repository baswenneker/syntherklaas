"""Unified writer interface — dispatches to the six output formats.

Formats:
- ``csv-loose``   : ``<output>`` is a dir; one ``<table>.csv`` per table
- ``xlsx-loose``  : ``<output>`` is a dir; one ``<table>.xlsx`` per table
- ``xlsx-multi``  : ``<output>`` is an .xlsx file; sheets in topo order
- ``sqlite``      : ``<output>`` is a .db / .sqlite file
- ``postgres``    : ``<output>`` is a .sql file (PostgreSQL dialect)
- ``mssql``       : ``<output>`` is a .sql file (Microsoft SQL Server dialect)
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import pandas as pd

import sql_writer
import sqlite_writer
import xlsx_writer
from xlsx_writer import EXCEL_ROW_LIMIT, RowLimitExceededError

SUPPORTED_FORMATS = frozenset(
    {"csv-loose", "xlsx-loose", "xlsx-multi", "sqlite", "postgres", "mssql"}
)


class WriterError(Exception):
    """Raised on unsupported format or invalid output target."""


def write(
    tables: Dict[str, pd.DataFrame],
    topo_order: List[str],
    output_path: str,
    fmt: str,
    schema_tables: Optional[List[Dict[str, Any]]] = None,
) -> None:
    if fmt not in SUPPORTED_FORMATS:
        raise WriterError(
            f"Unsupported format: {fmt!r}; expected one of {sorted(SUPPORTED_FORMATS)}"
        )

    if fmt == "csv-loose":
        _write_csv_loose(tables, topo_order, output_path)
    elif fmt == "xlsx-loose":
        _write_xlsx_loose(tables, topo_order, output_path)
    elif fmt == "xlsx-multi":
        xlsx_writer.write(tables, topo_order, output_path)
    elif fmt == "sqlite":
        if os.path.exists(output_path):
            raise WriterError(f"Output sqlite already exists: {output_path}")
        sqlite_writer.write(tables, topo_order, output_path)
    elif fmt in ("postgres", "mssql"):
        if os.path.exists(output_path):
            raise WriterError(f"Output SQL file already exists: {output_path}")
        sql_writer.write(
            tables, topo_order, output_path, dialect=fmt, schema_tables=schema_tables
        )


def _ensure_empty_dir(path: str) -> None:
    if os.path.isfile(path):
        raise WriterError(f"Output dir path points at a file: {path}")
    if os.path.isdir(path) and os.listdir(path):
        raise WriterError(f"Output dir not empty: {path}")
    os.makedirs(path, exist_ok=True)


def _write_csv_loose(
    tables: Dict[str, pd.DataFrame],
    topo_order: List[str],
    output_path: str,
) -> None:
    _ensure_empty_dir(output_path)
    for table in topo_order:
        tables[table].to_csv(os.path.join(output_path, f"{table}.csv"), index=False)


def _write_xlsx_loose(
    tables: Dict[str, pd.DataFrame],
    topo_order: List[str],
    output_path: str,
) -> None:
    over_limit = [(t, len(tables[t])) for t in topo_order if len(tables[t]) > EXCEL_ROW_LIMIT]
    if over_limit:
        raise RowLimitExceededError(
            f"Tables exceed Excel row limit of {EXCEL_ROW_LIMIT}: {over_limit}"
        )
    _ensure_empty_dir(output_path)
    for table in topo_order:
        out_path = os.path.join(output_path, f"{table}.xlsx")
        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            tables[table].to_excel(writer, sheet_name=table, index=False)
            writer.sheets[table].freeze_panes = "A2"

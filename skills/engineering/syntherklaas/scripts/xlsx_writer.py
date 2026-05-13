"""Write generated DataFrames to a multi-sheet .xlsx file.

Always-new (no append). Header row is frozen. Sheet order follows the supplied
topological order. Enforces Excel's 31-char sheet name and 1,048,576-row limits.
"""

from __future__ import annotations

import os
from typing import Dict, List

import pandas as pd

EXCEL_SHEET_NAME_MAX = 31
EXCEL_ROW_LIMIT = 1_048_576


class OutputExistsError(Exception):
    """Raised when the target .xlsx path already exists."""


class TableNameTooLongError(Exception):
    """Raised when a table name exceeds Excel's 31-char sheet-name limit."""


class RowLimitExceededError(Exception):
    """Raised when a single table exceeds Excel's per-sheet row limit."""


def _validate(
    tables: Dict[str, pd.DataFrame],
    topo_order: List[str],
    output_path: str,
) -> None:
    if os.path.exists(output_path):
        raise OutputExistsError(f"Output xlsx already exists: {output_path}")

    too_long = [t for t in topo_order if len(t) > EXCEL_SHEET_NAME_MAX]
    if too_long:
        raise TableNameTooLongError(
            f"Table name(s) exceed Excel's {EXCEL_SHEET_NAME_MAX}-char limit: {too_long}"
        )

    over_limit = [(t, len(tables[t])) for t in topo_order if len(tables[t]) > EXCEL_ROW_LIMIT]
    if over_limit:
        raise RowLimitExceededError(
            f"Tables exceed Excel row limit of {EXCEL_ROW_LIMIT}: {over_limit}"
        )


def write(
    tables: Dict[str, pd.DataFrame],
    topo_order: List[str],
    output_path: str,
) -> None:
    """Write tables to a multi-sheet .xlsx in topological order, header frozen."""
    _validate(tables, topo_order, output_path)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for table in topo_order:
            tables[table].to_excel(writer, sheet_name=table, index=False)
            writer.sheets[table].freeze_panes = "A2"

"""Step 1+2: foreign-key detection and topological ordering.

Resolution priority for each FK:
1. Existing DB schema (read via ``PRAGMA foreign_key_list`` in append-mode).
2. ``_relations`` override sheet/CSV provided by the user.
3. Auto-inferred from column naming (``*_id`` / ``*Id`` / ``*_ID``).

Cyclic and composite FKs raise; v1 supports neither.
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd


class CyclicForeignKeyError(Exception):
    """Raised when the FK graph contains a cycle that prevents topological ordering."""


class CompositeForeignKeyError(Exception):
    """Raised when a multi-column FK is detected; not supported in v1."""


@dataclass
class ForeignKey:
    column: str
    references_table: str
    references_column: str


FksByTable = Dict[str, List[ForeignKey]]


_FK_PATTERN = re.compile(r"^(.+?)(_id|Id|_ID)$")


def auto_infer_fks(tables: Dict[str, pd.DataFrame]) -> FksByTable:
    """Infer FK relations from column-name conventions."""
    table_lookup = {t.lower(): t for t in tables}
    result: FksByTable = {t: [] for t in tables}

    for table_name, df in tables.items():
        for col in df.columns:
            if col.lower() == "id":
                continue
            match = _FK_PATTERN.match(col)
            if not match:
                continue
            base = match.group(1).lower()
            candidates = [base, base + "s", base + "en", base + "ies"]
            matched = {table_lookup[c] for c in candidates if c in table_lookup}
            matched.discard(table_name)
            if len(matched) != 1:
                continue
            parent = next(iter(matched))
            if "id" in tables[parent].columns:
                result[table_name].append(
                    ForeignKey(column=col, references_table=parent, references_column="id")
                )
    return result


def parse_relations_override(overrides_df: Optional[pd.DataFrame]) -> FksByTable:
    """Parse the ``_relations`` sheet/CSV into a FksByTable.

    A column appearing twice within the same table indicates a composite FK
    declaration, which is not supported in v1.
    """
    if overrides_df is None or overrides_df.empty:
        return {}

    by_table: FksByTable = {}
    seen: set = set()
    for _, row in overrides_df.iterrows():
        key = (row["table"], row["column"])
        if key in seen:
            raise CompositeForeignKeyError(
                f"_relations declares {row['table']}.{row['column']} more than once; "
                "composite FKs are not supported in v1."
            )
        seen.add(key)
        by_table.setdefault(row["table"], []).append(
            ForeignKey(
                column=row["column"],
                references_table=row["references_table"],
                references_column=row["references_column"],
            )
        )
    return by_table


def read_db_fks(db_path: str, table_names: List[str]) -> FksByTable:
    """Read FK constraints from an existing SQLite DB.

    Returns an empty dict if the DB does not yet exist. Raises
    ``CompositeForeignKeyError`` if a composite FK is found.
    """
    if not db_path or not os.path.exists(db_path):
        return {}

    result: FksByTable = {}
    with sqlite3.connect(db_path) as conn:
        for table in table_names:
            try:
                rows = conn.execute(f"PRAGMA foreign_key_list('{table}')").fetchall()
            except sqlite3.OperationalError:
                continue
            if not rows:
                continue

            counts: Dict[int, int] = {}
            for row in rows:
                counts[row[0]] = counts.get(row[0], 0) + 1
            if any(c > 1 for c in counts.values()):
                raise CompositeForeignKeyError(
                    f"Existing DB table '{table}' has a composite FK; not supported."
                )

            result[table] = [
                ForeignKey(column=row[3], references_table=row[2], references_column=row[4])
                for row in rows
            ]
    return result


def resolve_fks(
    tables: Dict[str, pd.DataFrame],
    relations_override: Optional[pd.DataFrame],
    db_path: Optional[str] = None,
) -> FksByTable:
    """Combine sources into a single FK map. Priority: DB > override > auto."""
    auto = auto_infer_fks(tables)
    override = parse_relations_override(relations_override)
    db = read_db_fks(db_path, list(tables.keys())) if db_path else {}

    result: FksByTable = {}
    for table in tables:
        if db.get(table):
            result[table] = db[table]
        elif override.get(table):
            result[table] = override[table]
        else:
            result[table] = auto.get(table, [])
    return result


def topological_sort(table_names: List[str], fks: FksByTable) -> List[str]:
    """Return tables in parent-first order; self-references are skipped."""
    adjacency: Dict[str, List[str]] = {t: [] for t in table_names}
    in_degree: Dict[str, int] = {t: 0 for t in table_names}

    for child, fklist in fks.items():
        for fk in fklist:
            parent = fk.references_table
            if parent == child or parent not in adjacency:
                continue
            adjacency[parent].append(child)
            in_degree[child] += 1

    queue = [t for t, d in in_degree.items() if d == 0]
    ordered: List[str] = []
    while queue:
        t = queue.pop(0)
        ordered.append(t)
        for child in adjacency[t]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if len(ordered) != len(table_names):
        remaining = [t for t in table_names if t not in ordered]
        raise CyclicForeignKeyError(
            f"Cyclic FK detected; cannot order tables: {remaining}"
        )
    return ordered


def format_report(fks: FksByTable) -> str:
    lines = ["FK resolution:"]
    if not any(fks.values()):
        lines.append("  (none)")
        return "\n".join(lines)
    for table in sorted(fks):
        for fk in fks[table]:
            lines.append(
                f"  {table}.{fk.column} -> {fk.references_table}.{fk.references_column}"
            )
    return "\n".join(lines)

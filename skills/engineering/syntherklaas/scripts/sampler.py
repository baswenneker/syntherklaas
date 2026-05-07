"""Step 3: cap-only first-N sampling with FK-driven child filtering.

For tables with no outgoing FK (roots), apply ``df.head(max_rows)``.
For tables with outgoing FKs, filter rows whose FK value is in the set of
already-sampled parent IDs. No extra cap on children — they follow naturally.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

import pandas as pd

from fk_resolver import ForeignKey, FksByTable


def sample(
    tables: Dict[str, pd.DataFrame],
    fks: FksByTable,
    topo_order: List[str],
    max_rows: Optional[int],
    pk_column: str = "id",
) -> Dict[str, pd.DataFrame]:
    """Sample tables in topological order, preserving FK referential integrity."""
    sampled: Dict[str, pd.DataFrame] = {}
    sampled_ids: Dict[str, Set] = {}

    for table in topo_order:
        df = tables[table]

        outgoing: List[ForeignKey] = [
            fk for fk in fks.get(table, []) if fk.references_table != table
        ]

        for fk in outgoing:
            parent_ids = sampled_ids.get(fk.references_table)
            if parent_ids is None:
                continue
            df = df[df[fk.column].isin(parent_ids)]

        if max_rows is not None and not outgoing:
            df = df.head(max_rows)

        df = df.reset_index(drop=True)
        sampled[table] = df
        if pk_column in df.columns:
            sampled_ids[table] = set(df[pk_column].tolist())

    return sampled


def format_report(
    original: Dict[str, pd.DataFrame],
    sampled: Dict[str, pd.DataFrame],
) -> str:
    lines = ["Row counts:"]
    for table in sorted(original):
        before = len(original[table])
        after = len(sampled.get(table, original[table]))
        lines.append(f"  {table}: {before} -> {after}")
    return "\n".join(lines)

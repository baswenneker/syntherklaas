"""Topological ordering of tables based on FK relations.

Generator emits parents before children so FK columns can reference already-
generated parent IDs. Self-references are skipped (the parent of a row is in
the same table; we treat the child column as a regular value column for ordering
purposes). Composite/cyclic FK chains are not supported.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


class CyclicForeignKeyError(Exception):
    """Raised when the FK graph contains a cycle that prevents topological ordering."""


@dataclass
class ForeignKey:
    column: str
    references_table: str
    references_column: str


FksByTable = Dict[str, List[ForeignKey]]


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

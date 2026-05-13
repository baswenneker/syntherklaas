"""Generate synthetic data from a schema-YAML file.

CLI:
    --schema <path>             required; path to schema YAML
    --output <path>             output path (file or dir, format-dependent)
    --format <fmt>              csv-loose | xlsx-loose | xlsx-multi | sqlite
    --preview                   skip writers; dump 10 rows/table as JSON to stdout

Determinism: seed = schema.seed if present, else SHA256(schema-bytes)[:8] as int.

Exit codes:
    0 — success
    2 — schema/output/format problem
    3 — cyclic FK
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from fk_resolver import (
    CyclicForeignKeyError,
    ForeignKey,
    FksByTable,
    topological_sort,
)  # noqa: I001
from providers import Generator
from schema import SchemaError, load_schema
from writers import WriterError, write as writers_write
from xlsx_writer import (
    OutputExistsError,
    RowLimitExceededError,
    TableNameTooLongError,
)

PREVIEW_ROWS = 10


def main(argv: List[str]) -> int:
    args = _parse_args(argv)

    try:
        schema = load_schema(args.schema)
    except SchemaError as e:
        print(f"Schema error: {e}", file=sys.stderr)
        return 2

    seed = _derive_seed(schema, args.schema)
    generator = Generator(locale=schema.get("locale", "nl_NL"), seed=seed)

    try:
        topo_order = _build_topo(schema)
    except CyclicForeignKeyError as e:
        print(f"FK error: {e}", file=sys.stderr)
        return 3

    tables = _generate_tables(schema, topo_order, generator)

    if args.preview:
        _emit_preview(tables, topo_order)
        return 0

    output_path = args.output or schema.get("output", {}).get("path")
    output_fmt = args.format or schema.get("output", {}).get("format")
    if not output_path or not output_fmt:
        print(
            "--output and --format are required unless --preview "
            "(or set 'output' block in schema)",
            file=sys.stderr,
        )
        return 2

    try:
        writers_write(tables, topo_order, output_path, output_fmt)
    except (
        WriterError,
        OutputExistsError,
        TableNameTooLongError,
        RowLimitExceededError,
    ) as e:
        print(f"Writer error: {e}", file=sys.stderr)
        return 2

    print(_format_report(tables, topo_order, output_path, output_fmt))
    return 0


# -- argparse -------------------------------------------------------------


def _parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="syntherklaas-generate")
    p.add_argument("--schema", required=True, help="Path to schema YAML")
    p.add_argument("--output", help="Output file or directory")
    p.add_argument(
        "--format",
        choices=["csv-loose", "xlsx-loose", "xlsx-multi", "sqlite"],
        help="Output format",
    )
    p.add_argument(
        "--preview",
        action="store_true",
        help="Print 10-row JSON preview to stdout; do not write files",
    )
    return p.parse_args(argv)


# -- seed + topo ---------------------------------------------------------


def _derive_seed(schema: Dict[str, Any], schema_path: str) -> int:
    if "seed" in schema:
        return int(schema["seed"])
    data = Path(schema_path).read_bytes()
    digest = hashlib.sha256(data).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _build_topo(schema: Dict[str, Any]) -> List[str]:
    tables = schema["tables"]
    names = [t["name"] for t in tables]
    fks: FksByTable = {n: [] for n in names}
    for t in tables:
        for col in t["columns"]:
            if col["provider"] == "fk":
                parent_table, _, parent_col = col["references"].partition(".")
                fks[t["name"]].append(
                    ForeignKey(
                        column=col["name"],
                        references_table=parent_table,
                        references_column=parent_col,
                    )
                )
    return topological_sort(names, fks)


# -- generation ----------------------------------------------------------


def _generate_tables(
    schema: Dict[str, Any],
    topo_order: List[str],
    generator: Generator,
) -> Dict[str, pd.DataFrame]:
    by_name = {t["name"]: t for t in schema["tables"]}
    out: Dict[str, pd.DataFrame] = {}

    for table_name in topo_order:
        tbl = by_name[table_name]
        volume = tbl["volume"]

        if "per_parent" in volume:
            df = _generate_per_parent(tbl, volume["per_parent"], out, generator)
        else:
            df = _generate_count(tbl, volume["count"], out, generator)

        out[table_name] = df

    return out


def _generate_count(
    tbl: Dict[str, Any],
    count_spec: Dict[str, Any],
    already: Dict[str, pd.DataFrame],
    generator: Generator,
) -> pd.DataFrame:
    n = generator.draw_count(count_spec)
    return _build_dataframe(tbl, n, {}, already, generator)


def _generate_per_parent(
    tbl: Dict[str, Any],
    spec: Dict[str, Any],
    already: Dict[str, pd.DataFrame],
    generator: Generator,
) -> pd.DataFrame:
    parent_table = spec["parent"]
    parent_fks = [
        c for c in tbl["columns"]
        if c["provider"] == "fk" and c["references"].startswith(parent_table + ".")
    ]
    if len(parent_fks) != 1:
        raise SchemaError(
            f"Table {tbl['name']!r} per_parent: exactly one FK to {parent_table!r} required, "
            f"found {len(parent_fks)}"
        )
    fk_col = parent_fks[0]
    _, _, parent_pk_col = fk_col["references"].partition(".")
    parent_ids = already[parent_table][parent_pk_col].tolist()

    fk_values: List[Any] = []
    for pid in parent_ids:
        k = generator.draw_count(spec)
        fk_values.extend([pid] * k)

    return _build_dataframe(tbl, len(fk_values), {fk_col["name"]: fk_values}, already, generator)


def _build_dataframe(
    tbl: Dict[str, Any],
    n: int,
    fk_overrides: Dict[str, List[Any]],
    already: Dict[str, pd.DataFrame],
    generator: Generator,
) -> pd.DataFrame:
    data: Dict[str, List[Any]] = {}

    for col in tbl["columns"]:
        col_name = col["name"]
        provider = col["provider"]

        if col_name in fk_overrides:
            data[col_name] = fk_overrides[col_name]
            continue

        if provider == "sequential":
            data[col_name] = list(range(1, n + 1))
            continue

        if provider == "fk":
            parent_table, _, parent_col = col["references"].partition(".")
            parent_ids = already[parent_table][parent_col].tolist()
            data[col_name] = generator.column_values(col, n, ctx={"parent_ids": parent_ids})
            continue

        data[col_name] = generator.column_values(col, n)

    return pd.DataFrame(data)


# -- preview + report ---------------------------------------------------


def _emit_preview(tables: Dict[str, pd.DataFrame], topo_order: List[str]) -> None:
    out: Dict[str, Any] = {}
    for table in topo_order:
        df = tables[table].head(PREVIEW_ROWS)
        out[table] = {
            "row_count_total": int(len(tables[table])),
            "columns": list(df.columns),
            "rows": df.to_dict(orient="records"),
        }
    json.dump(out, sys.stdout, default=_json_default, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    raise TypeError(f"Not JSON-serializable: {type(obj).__name__}")


def _format_report(
    tables: Dict[str, pd.DataFrame],
    topo_order: List[str],
    output_path: str,
    fmt: str,
) -> str:
    lines = [f"Wrote {fmt} -> {output_path}"]
    for t in topo_order:
        lines.append(f"  {t}: {len(tables[t])} rows")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

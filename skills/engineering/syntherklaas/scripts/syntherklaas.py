"""CLI entry point. Orchestrates: detect → resolve → sample → anonymize → write."""

from __future__ import annotations

import argparse
import glob
import os
import pathlib
import sys
from typing import Dict, Optional, Tuple

import pandas as pd

from anonymizer import anonymize_dataframe, build_faker
from detector import build_analyzer, detect_all, format_report as format_pii_report
from fk_resolver import (
    CompositeForeignKeyError,
    CyclicForeignKeyError,
    format_report as format_fk_report,
    resolve_fks,
    topological_sort,
)
from sampler import format_report as format_sample_report, sample
from sqlite_writer import (
    SchemaMismatchError,
    format_report as format_sqlite_report,
    write as sqlite_write,
)
from xlsx_writer import (
    OutputExistsError,
    TableNameTooLongError,
    format_report as format_xlsx_report,
    write as xlsx_write,
)

SQLITE_EXTS = (".db", ".sqlite")
XLSX_EXTS = (".xlsx",)
SUPPORTED_EXTS = SQLITE_EXTS + XLSX_EXTS

EXIT_OK = 0
EXIT_SCHEMA_MISMATCH = 2
EXIT_FK_ERROR = 3
EXIT_DEPS = 4


def load_input(
    path: str,
) -> Tuple[Dict[str, pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Load tables + meta sheets from an Excel file or CSV directory."""
    if os.path.isfile(path):
        all_sheets = pd.read_excel(path, sheet_name=None)
    elif os.path.isdir(path):
        all_sheets = {}
        for csv_path in sorted(glob.glob(os.path.join(path, "*.csv"))):
            name = os.path.splitext(os.path.basename(csv_path))[0]
            all_sheets[name] = pd.read_csv(csv_path)
    else:
        raise FileNotFoundError(f"Input not found: {path}")

    relations = all_sheets.pop("_relations", None)
    pii_config = all_sheets.pop("_pii_config", None)
    return all_sheets, relations, pii_config


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="syntherklaas",
        description="Synthetic data pipeline: Excel/CSV -> PII-anonymize -> SQLite or XLSX.",
    )
    parser.add_argument("--input", required=True, help="Path to .xlsx or directory of .csv files")
    parser.add_argument(
        "--output",
        required=True,
        help="Path to output file. Format inferred from extension: "
        ".db/.sqlite -> SQLite, .xlsx -> Excel.",
    )
    parser.add_argument("--max-rows", type=int, default=None, help="Cap root tables at N rows")
    parser.add_argument(
        "--mode",
        choices=["auto", "append", "new"],
        default="auto",
        help="auto (default): append if output exists else create new. "
        "append: require output exists (SQLite only; xlsx output is new-only). "
        "new: require output does not exist.",
    )
    parser.add_argument(
        "--spacy-model",
        default="nl_core_news_md",
        help="Spacy NL model name (default: nl_core_news_md)",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    output_ext = pathlib.Path(args.output).suffix.lower()
    if output_ext not in SUPPORTED_EXTS:
        print(
            f"ERROR: unsupported output extension '{output_ext}'. "
            f"Use one of {SUPPORTED_EXTS}.",
            file=sys.stderr,
        )
        return EXIT_SCHEMA_MISMATCH

    if os.path.exists(args.input) and os.path.exists(args.output) and (
        os.path.realpath(args.input) == os.path.realpath(args.output)
    ):
        print("ERROR: input and output paths are identical", file=sys.stderr)
        return EXIT_SCHEMA_MISMATCH

    is_xlsx = output_ext in XLSX_EXTS
    output_exists = os.path.exists(args.output)

    if is_xlsx and args.mode == "append":
        print(
            "ERROR: --mode append is not supported for xlsx output (xlsx is new-only)",
            file=sys.stderr,
        )
        return EXIT_SCHEMA_MISMATCH

    if is_xlsx and output_exists:
        print(f"ERROR: output xlsx already exists: {args.output}", file=sys.stderr)
        return EXIT_SCHEMA_MISMATCH

    if not is_xlsx:
        if args.mode == "new" and output_exists:
            print(
                f"ERROR: --mode new but output already exists: {args.output}",
                file=sys.stderr,
            )
            return EXIT_SCHEMA_MISMATCH
        if args.mode == "append" and not output_exists:
            print(
                f"ERROR: --mode append but output does not exist: {args.output}",
                file=sys.stderr,
            )
            return EXIT_SCHEMA_MISMATCH

    tables, relations_df, pii_config_df = load_input(args.input)
    print(f"Loaded {len(tables)} tables from {args.input}:")
    for t, df in tables.items():
        print(f"  {t}: {len(df)} rows, columns={list(df.columns)}")
    print()

    print("Building Presidio analyzer (loads Spacy NL model)...")
    try:
        analyzer = build_analyzer(args.spacy_model)
    except Exception as exc:
        print(f"ERROR loading Spacy model '{args.spacy_model}': {exc}", file=sys.stderr)
        print("Hint: run `uv run python -m spacy download nl_core_news_md`", file=sys.stderr)
        return EXIT_DEPS

    pii_map = detect_all(tables, pii_config_df, analyzer)
    print(format_pii_report(pii_map, tables))
    print()

    db_path_for_fks = args.output if (output_exists and not is_xlsx) else None
    try:
        fks = resolve_fks(tables, relations_df, db_path_for_fks)
        topo_order = topological_sort(list(tables.keys()), fks)
    except (CompositeForeignKeyError, CyclicForeignKeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_FK_ERROR

    print(format_fk_report(fks))
    print(f"Topological order: {' -> '.join(topo_order)}")
    print()

    sampled = sample(tables, fks, topo_order, args.max_rows)
    print(format_sample_report(tables, sampled))
    print()

    faker = build_faker()
    entity_mapping: Dict[str, Dict[str, str]] = {}
    anonymized: Dict[str, pd.DataFrame] = {}
    for table in topo_order:
        anonymized[table] = anonymize_dataframe(
            sampled[table], table, pii_map, entity_mapping, faker
        )
    total_unique = sum(len(bucket) for bucket in entity_mapping.values())
    print(
        f"Anonymized {total_unique} unique values across "
        f"{len(entity_mapping)} entity types: {sorted(entity_mapping.keys())}"
    )
    print()

    try:
        if is_xlsx:
            id_map = xlsx_write(anonymized, fks, topo_order, args.output)
            print(format_xlsx_report(id_map))
        else:
            id_map = sqlite_write(anonymized, fks, topo_order, args.output)
            print(format_sqlite_report(id_map))
    except (SchemaMismatchError, OutputExistsError, TableNameTooLongError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_SCHEMA_MISMATCH

    print(f"\nDone. Written to {args.output}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

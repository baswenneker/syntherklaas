"""Step 1: detect PII columns across all input tables.

Combines Presidio's structured pandas analysis with custom NL recognizers,
then applies user-provided `_pii_config` overrides (force/skip per column).
"""

from __future__ import annotations

from typing import Dict, Optional, Set, Tuple

import pandas as pd

from nl_recognizers import is_valid_bsn, register_nl_recognizers


PiiMap = Dict[Tuple[str, str], str]  # (table, column) -> entity_type

# Column-name aliases that unambiguously identify a BSN column even when the
# values are numeric (and therefore skipped by the text-only Presidio path).
_BSN_COLUMN_ALIASES = frozenset({"bsn", "burgerservicenummer", "sofinummer", "sofi"})

# Fraction of non-null values that must pass the 11-proof for a numeric column
# to be classified as BSN. Tuned to be high enough that random 9-digit IDs do
# not flip the column, but tolerant of a few stray invalid entries.
_BSN_NUMERIC_THRESHOLD = 0.8


def build_analyzer(spacy_model: str = "nl_core_news_md"):
    """Build an NL-configured Presidio AnalyzerEngine with our custom recognizers."""
    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    nlp_configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "nl", "model_name": spacy_model}],
    }
    nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()

    registry = RecognizerRegistry(supported_languages=["nl"])
    registry.load_predefined_recognizers(languages=["nl"])
    register_nl_recognizers(registry)

    return AnalyzerEngine(
        nlp_engine=nlp_engine,
        registry=registry,
        supported_languages=["nl"],
    )


def _normalize_column_name(name) -> str:
    """Lowercase alphanumerics-only form for fuzzy column-name matching."""
    return "".join(c.lower() for c in str(name) if c.isalnum())


def _columns_named_like_bsn(df: pd.DataFrame) -> Set[str]:
    """Columns whose name matches a known BSN alias (case/punctuation-insensitive)."""
    return {col for col in df.columns if _normalize_column_name(col) in _BSN_COLUMN_ALIASES}


def _numeric_columns_with_bsn_values(
    df: pd.DataFrame, min_fraction: float = _BSN_NUMERIC_THRESHOLD
) -> Set[str]:
    """Numeric columns whose non-null values are predominantly 9-digit BSNs.

    Covers the case where Excel left BSN cells as numbers instead of text, so
    pandas typed the column as int/float and the text-only Presidio path
    skipped it. Leading-zero BSNs are unrecoverable from this representation,
    but those would not pass the 9-digit length check anyway — relying on
    column-name hints to catch that subset.
    """
    result: Set[str] = set()
    numeric_columns = df.select_dtypes(include=["number"]).columns
    for col in numeric_columns:
        values = df[col].dropna()
        if len(values) == 0:
            continue
        valid = 0
        for v in values:
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if not f.is_integer():
                continue
            i = int(f)
            if 100_000_000 <= i <= 999_999_999 and is_valid_bsn(str(i)):
                valid += 1
        if valid / len(values) >= min_fraction:
            result.add(col)
    return result


def detect_pii_for_table(df: pd.DataFrame, analyzer) -> Dict[str, str]:
    """Run presidio-structured analysis on a single DataFrame.

    Text columns go through Presidio. Numeric columns are scanned separately
    for BSN — Presidio can only see strings, so a column Excel exported as
    numbers (no text formatting) would otherwise slip through.

    Returns: ``{column_name: entity_type}`` for columns where PII was detected.
    """
    from presidio_structured import PandasAnalysisBuilder

    detected: Dict[str, str] = {}

    text_columns = df.select_dtypes(include=["object", "string"]).columns
    if len(text_columns) > 0:
        text_df = df[text_columns]
        builder = PandasAnalysisBuilder(analyzer=analyzer)
        analysis = builder.generate_analysis(text_df, language="nl")
        detected.update({col: ent for col, ent in analysis.entity_mapping.items() if ent})

    bsn_fallback = _columns_named_like_bsn(df) | _numeric_columns_with_bsn_values(df)
    for col in bsn_fallback:
        detected.setdefault(col, "BSN")

    return detected


def apply_pii_overrides(
    detected: Dict[str, str],
    overrides_df: Optional[pd.DataFrame],
    table: str,
) -> Dict[str, str]:
    """Apply `_pii_config` overrides for one table.

    Override rows have columns: table | column | pii_type | strategy.
    `strategy=force` overwrites detection; `strategy=skip` (or `pii_type=NONE`) removes.
    """
    if overrides_df is None or overrides_df.empty:
        return detected

    result = dict(detected)
    table_rows = overrides_df[overrides_df["table"] == table]
    for _, row in table_rows.iterrows():
        column = row["column"]
        strategy = str(row.get("strategy", "force")).lower()
        pii_type = str(row.get("pii_type", "")).upper()
        if strategy == "skip" or pii_type == "NONE":
            result.pop(column, None)
        elif strategy == "force":
            result[column] = pii_type
    return result


def detect_all(
    tables: Dict[str, pd.DataFrame],
    overrides_df: Optional[pd.DataFrame],
    analyzer,
) -> PiiMap:
    """Detect PII for every table; merge with overrides."""
    result: PiiMap = {}
    for table_name, df in tables.items():
        detected = detect_pii_for_table(df, analyzer)
        finalized = apply_pii_overrides(detected, overrides_df, table_name)
        for column, pii_type in finalized.items():
            result[(table_name, column)] = pii_type
    return result


def format_report(pii_map: PiiMap, tables: Dict[str, pd.DataFrame]) -> str:
    """Human-readable PII detection report."""
    lines = ["PII detection:"]
    for table in sorted(tables):
        cols = [(c, t) for (tbl, c), t in pii_map.items() if tbl == table]
        if not cols:
            lines.append(f"  {table}: (none)")
            continue
        for col, ent in sorted(cols):
            lines.append(f"  {table}.{col}: {ent}")
    return "\n".join(lines)

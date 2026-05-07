"""Step 1: detect PII columns across all input tables.

Combines Presidio's structured pandas analysis with custom NL recognizers,
then applies user-provided `_pii_config` overrides (force/skip per column).
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import pandas as pd

from nl_recognizers import register_nl_recognizers


PiiMap = Dict[Tuple[str, str], str]  # (table, column) -> entity_type


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


def detect_pii_for_table(df: pd.DataFrame, analyzer) -> Dict[str, str]:
    """Run presidio-structured analysis on a single DataFrame.

    Only object/string-typed columns are analyzed; numeric and datetime columns
    are never PII and would otherwise yield spurious detections (numeric IDs
    matching DATE_TIME patterns, etc).

    Returns: ``{column_name: entity_type}`` for columns where PII was detected.
    """
    from presidio_structured import PandasAnalysisBuilder

    text_columns = df.select_dtypes(include=["object", "string"]).columns
    if len(text_columns) == 0:
        return {}
    text_df = df[text_columns]

    builder = PandasAnalysisBuilder(analyzer=analyzer)
    analysis = builder.generate_analysis(text_df, language="nl")
    return {col: ent for col, ent in analysis.entity_mapping.items() if ent}


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

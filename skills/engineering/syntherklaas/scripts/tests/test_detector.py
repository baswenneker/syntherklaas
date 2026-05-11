"""Detector fallback paths for BSN columns missed by Presidio's text-only analysis."""

from __future__ import annotations

import pandas as pd

from detector import (
    _columns_named_like_bsn,
    _numeric_columns_with_bsn_values,
    detect_pii_for_table,
)

# 11-proof valid BSNs (verified by tests/test_bsn.py).
VALID_BSNS = [100000009, 111222333, 123456782, 192837465, 287654321]


def test_columns_named_like_bsn_matches_aliases():
    df = pd.DataFrame(
        {
            "BSN": [1, 2],
            "Burgerservicenummer": [1, 2],
            "sofi_nummer": [1, 2],
            "klant_id": [1, 2],
            "naam": ["a", "b"],
        }
    )
    assert _columns_named_like_bsn(df) == {"BSN", "Burgerservicenummer", "sofi_nummer"}


def test_columns_named_like_bsn_ignores_unrelated_names():
    df = pd.DataFrame({"id": [1], "email": ["x@y.nl"], "BSN_label": ["foo"]})
    assert _columns_named_like_bsn(df) == set()


def test_numeric_column_of_valid_bsns_detected():
    df = pd.DataFrame({"nummer": VALID_BSNS})
    assert _numeric_columns_with_bsn_values(df) == {"nummer"}


def test_numeric_column_of_random_ids_not_detected():
    df = pd.DataFrame({"klant_id": [1, 2, 3, 4, 5]})
    assert _numeric_columns_with_bsn_values(df) == set()


def test_numeric_column_below_threshold_not_detected():
    # Only 1 valid out of 5 — well below the 80% floor.
    df = pd.DataFrame({"misc": VALID_BSNS[:1] + [1, 2, 3, 4]})
    assert _numeric_columns_with_bsn_values(df) == set()


def test_numeric_column_with_nan_tolerated():
    df = pd.DataFrame({"bsn": VALID_BSNS + [None, None]})
    assert _numeric_columns_with_bsn_values(df) == {"bsn"}


def test_text_column_of_bsns_not_returned_by_numeric_helper():
    df = pd.DataFrame({"bsn": [str(b) for b in VALID_BSNS]})
    assert _numeric_columns_with_bsn_values(df) == set()


def test_empty_dataframe_safe():
    assert _numeric_columns_with_bsn_values(pd.DataFrame()) == set()
    assert _columns_named_like_bsn(pd.DataFrame()) == set()


def test_detect_pii_for_table_finds_numeric_bsn_without_analyzer():
    """Numeric-only DataFrame: analyzer is never invoked, only the fallback runs."""
    df = pd.DataFrame({"id": [1, 2, 3, 4, 5], "nummer": VALID_BSNS})
    # Analyzer would be invoked only if text columns existed; pass None to prove it.
    result = detect_pii_for_table(df, analyzer=None)
    assert result == {"nummer": "BSN"}


def test_detect_pii_for_table_finds_named_bsn_column_even_when_numeric():
    df = pd.DataFrame({"id": [1, 2, 3], "BSN": [1, 2, 3]})
    result = detect_pii_for_table(df, analyzer=None)
    assert result.get("BSN") == "BSN"

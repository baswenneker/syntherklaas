"""Detector fallback paths and column-name overrides.

Two related concerns:
- BSN columns missed by Presidio's text-only analysis (numeric dtype or
  named-but-misclassified columns).
- Dutch split-name columns (voornaam / tussenvoegsel / achternaam) where the
  column name is a stronger signal than Presidio's PERSON heuristic.
"""

from __future__ import annotations

import pandas as pd

from detector import (
    _columns_named_like_bsn,
    _numeric_columns_with_bsn_values,
    _split_name_column_overrides,
    detect_pii_for_table,
)

# 11-proof valid BSNs (verified by tests/test_bsn.py).
VALID_BSNS = [100000009, 111222333, 123456782, 192837465, 287654321]


# ---------------------------------------------------------------------------
# BSN fallback paths
# ---------------------------------------------------------------------------


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
    result = detect_pii_for_table(df, analyzer=None)
    assert result == {"nummer": "BSN"}


def test_detect_pii_for_table_finds_named_bsn_column_even_when_numeric():
    df = pd.DataFrame({"id": [1, 2, 3], "BSN": [1, 2, 3]})
    result = detect_pii_for_table(df, analyzer=None)
    assert result.get("BSN") == "BSN"


# ---------------------------------------------------------------------------
# Split-name column overrides
# ---------------------------------------------------------------------------


def test_split_name_overrides_match_dutch_aliases():
    df = pd.DataFrame(
        {
            "voornaam": ["Jan"],
            "tussenvoegsel": ["van der"],
            "achternaam": ["Vries"],
            "klant_id": [1],
        }
    )
    assert _split_name_column_overrides(df) == {
        "voornaam": "NL_VOORNAAM",
        "tussenvoegsel": "NL_TUSSENVOEGSEL",
        "achternaam": "NL_ACHTERNAAM",
    }


def test_split_name_overrides_match_english_aliases():
    df = pd.DataFrame(
        {
            "FirstName": ["Jan"],
            "last_name": ["Vries"],
            "surname": ["Bosch"],
            "given_name": ["Anna"],
        }
    )
    overrides = _split_name_column_overrides(df)
    assert overrides["FirstName"] == "NL_VOORNAAM"
    assert overrides["last_name"] == "NL_ACHTERNAAM"
    assert overrides["surname"] == "NL_ACHTERNAAM"
    assert overrides["given_name"] == "NL_VOORNAAM"


def test_split_name_overrides_ignore_unrelated_columns():
    df = pd.DataFrame({"id": [1], "email": ["a@b.nl"], "naam": ["Jan Jansen"]})
    assert _split_name_column_overrides(df) == {}


def test_detect_pii_for_table_overrides_presidio_for_split_columns():
    """Override fires for split-name columns regardless of Presidio."""
    df = pd.DataFrame({"voornaam": [1], "tussenvoegsel": [2], "achternaam": [3]})
    result = detect_pii_for_table(df, analyzer=None)
    assert result == {
        "voornaam": "NL_VOORNAAM",
        "tussenvoegsel": "NL_TUSSENVOEGSEL",
        "achternaam": "NL_ACHTERNAAM",
    }

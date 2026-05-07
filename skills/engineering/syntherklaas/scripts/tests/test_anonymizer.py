"""Mapping consistency cross-row and cross-table."""

from __future__ import annotations

import pandas as pd

from anonymizer import anonymize_dataframe, build_faker


def test_consistent_within_table():
    df = pd.DataFrame({"naam": ["Jan", "Jan", "Anna"]})
    pii_map = {("klanten", "naam"): "PERSON"}
    entity_mapping: dict = {}
    out = anonymize_dataframe(df, "klanten", pii_map, entity_mapping, build_faker())

    assert out.iloc[0]["naam"] == out.iloc[1]["naam"]
    assert out.iloc[0]["naam"] != out.iloc[2]["naam"]
    assert out.iloc[0]["naam"] != "Jan"


def test_consistent_cross_table_via_shared_mapping():
    klanten = pd.DataFrame({"naam": ["Jan"]})
    orders = pd.DataFrame({"klant_naam": ["Jan"]})
    pii_map = {
        ("klanten", "naam"): "PERSON",
        ("orders", "klant_naam"): "PERSON",
    }
    entity_mapping: dict = {}
    faker = build_faker()

    out_klanten = anonymize_dataframe(klanten, "klanten", pii_map, entity_mapping, faker)
    out_orders = anonymize_dataframe(orders, "orders", pii_map, entity_mapping, faker)

    assert out_klanten.iloc[0]["naam"] == out_orders.iloc[0]["klant_naam"]


def test_non_pii_columns_unchanged():
    df = pd.DataFrame({"id": [1, 2, 3], "naam": ["Jan", "Anna", "Tim"]})
    pii_map = {("klanten", "naam"): "PERSON"}
    entity_mapping: dict = {}
    out = anonymize_dataframe(df, "klanten", pii_map, entity_mapping, build_faker())

    assert list(out["id"]) == [1, 2, 3]
    assert list(out["naam"]) != ["Jan", "Anna", "Tim"]


def test_email_replaced_fully():
    df = pd.DataFrame({"email": ["jan@bedrijf.nl"]})
    pii_map = {("klanten", "email"): "EMAIL_ADDRESS"}
    entity_mapping: dict = {}
    out = anonymize_dataframe(df, "klanten", pii_map, entity_mapping, build_faker())

    assert out.iloc[0]["email"] != "jan@bedrijf.nl"
    assert "@" in out.iloc[0]["email"]


def test_nan_passthrough():
    df = pd.DataFrame({"naam": ["Jan", None, "Anna"]})
    pii_map = {("klanten", "naam"): "PERSON"}
    entity_mapping: dict = {}
    out = anonymize_dataframe(df, "klanten", pii_map, entity_mapping, build_faker())

    assert pd.isna(out.iloc[1]["naam"])
    assert out.iloc[0]["naam"] != "Jan"

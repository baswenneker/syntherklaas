"""FK auto-inference, override parsing, topological sort, cyclic / composite detection."""

from __future__ import annotations

import pandas as pd
import pytest

from fk_resolver import (
    CompositeForeignKeyError,
    CyclicForeignKeyError,
    ForeignKey,
    auto_infer_fks,
    parse_relations_override,
    resolve_fks,
    topological_sort,
)


def test_auto_infer_basic():
    tables = {
        "klanten": pd.DataFrame({"id": [1], "naam": ["Jan"]}),
        "orders": pd.DataFrame({"id": [1], "klant_id": [1]}),
    }
    fks = auto_infer_fks(tables)
    assert len(fks["orders"]) == 1
    assert fks["orders"][0].column == "klant_id"
    assert fks["orders"][0].references_table == "klanten"


def test_auto_infer_plural_match():
    tables = {
        "categorieen": pd.DataFrame({"id": [1]}),
        "producten": pd.DataFrame({"id": [1], "categorie_id": [1]}),
    }
    fks = auto_infer_fks(tables)
    assert any(fk.references_table == "categorieen" for fk in fks["producten"])


def test_auto_infer_no_match():
    tables = {
        "users": pd.DataFrame({"id": [1]}),
        "orders": pd.DataFrame({"id": [1], "customer_id": [1]}),
    }
    fks = auto_infer_fks(tables)
    assert fks["orders"] == []


def test_topological_sort_ordering():
    table_names = ["orderlines", "klanten", "orders"]
    fks = {
        "klanten": [],
        "orders": [ForeignKey("klant_id", "klanten", "id")],
        "orderlines": [ForeignKey("order_id", "orders", "id")],
    }
    order = topological_sort(table_names, fks)
    assert order.index("klanten") < order.index("orders")
    assert order.index("orders") < order.index("orderlines")


def test_cyclic_detected():
    fks = {
        "a": [ForeignKey("b_id", "b", "id")],
        "b": [ForeignKey("a_id", "a", "id")],
    }
    with pytest.raises(CyclicForeignKeyError):
        topological_sort(["a", "b"], fks)


def test_self_reference_allowed():
    fks = {"employees": [ForeignKey("manager_id", "employees", "id")]}
    order = topological_sort(["employees"], fks)
    assert order == ["employees"]


def test_relations_override_parsed():
    overrides = pd.DataFrame(
        {
            "table": ["orders"],
            "column": ["customer_fk"],
            "references_table": ["users"],
            "references_column": ["id"],
        }
    )
    parsed = parse_relations_override(overrides)
    assert parsed["orders"][0].references_table == "users"


def test_composite_fk_rejected():
    overrides = pd.DataFrame(
        {
            "table": ["x", "x"],
            "column": ["a_id", "a_id"],
            "references_table": ["y", "y"],
            "references_column": ["a", "b"],
        }
    )
    with pytest.raises(CompositeForeignKeyError):
        parse_relations_override(overrides)


def test_resolve_priority_override_beats_auto():
    tables = {
        "klanten": pd.DataFrame({"id": [1]}),
        "orders": pd.DataFrame({"id": [1], "klant_id": [1]}),
    }
    overrides = pd.DataFrame(
        {
            "table": ["orders"],
            "column": ["klant_id"],
            "references_table": ["klanten"],
            "references_column": ["id"],
        }
    )
    fks = resolve_fks(tables, overrides, db_path=None)
    assert len(fks["orders"]) == 1

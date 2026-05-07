"""ID-offset, FK rewrite, and schema-mismatch checks."""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from fk_resolver import ForeignKey
from sqlite_writer import SchemaMismatchError, write


def test_id_offset_new_db(tmp_path):
    db = str(tmp_path / "new.db")
    sampled = {
        "klanten": pd.DataFrame({"id": [1, 2], "naam": ["A", "B"]}),
        "orders": pd.DataFrame({"id": [10, 11], "klant_id": [1, 2]}),
    }
    fks = {
        "klanten": [],
        "orders": [ForeignKey("klant_id", "klanten", "id")],
    }

    id_map = write(sampled, fks, ["klanten", "orders"], db)

    assert id_map["klanten"] == {1: 1, 2: 2}
    assert id_map["orders"] == {10: 1, 11: 2}

    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT id, klant_id FROM orders ORDER BY id").fetchall()
        assert rows == [(1, 1), (2, 2)]


def test_id_offset_append(tmp_path):
    db = str(tmp_path / "append.db")
    sampled1 = {"klanten": pd.DataFrame({"id": [1, 2], "naam": ["A", "B"]})}
    write(sampled1, {"klanten": []}, ["klanten"], db)

    sampled2 = {"klanten": pd.DataFrame({"id": [1, 2], "naam": ["C", "D"]})}
    id_map = write(sampled2, {"klanten": []}, ["klanten"], db)

    assert id_map["klanten"] == {1: 3, 2: 4}

    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT id, naam FROM klanten ORDER BY id").fetchall()
        assert rows == [(1, "A"), (2, "B"), (3, "C"), (4, "D")]


def test_fk_rewrite_on_append(tmp_path):
    db = str(tmp_path / "fk-append.db")
    fks = {
        "klanten": [],
        "orders": [ForeignKey("klant_id", "klanten", "id")],
    }

    sampled1 = {
        "klanten": pd.DataFrame({"id": [1, 2], "naam": ["A", "B"]}),
        "orders": pd.DataFrame({"id": [10, 11], "klant_id": [1, 2]}),
    }
    write(sampled1, fks, ["klanten", "orders"], db)

    sampled2 = {
        "klanten": pd.DataFrame({"id": [1, 2], "naam": ["C", "D"]}),
        "orders": pd.DataFrame({"id": [10, 11], "klant_id": [1, 2]}),
    }
    id_map = write(sampled2, fks, ["klanten", "orders"], db)

    assert id_map["klanten"] == {1: 3, 2: 4}
    assert id_map["orders"] == {10: 3, 11: 4}

    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT id, klant_id FROM orders ORDER BY id").fetchall()
        assert rows == [(1, 1), (2, 2), (3, 3), (4, 4)]


def test_schema_mismatch_fails(tmp_path):
    db = str(tmp_path / "mismatch.db")
    sampled1 = {"klanten": pd.DataFrame({"id": [1], "naam": ["A"]})}
    write(sampled1, {"klanten": []}, ["klanten"], db)

    sampled2 = {"klanten": pd.DataFrame({"id": [1], "email": ["x@y.nl"]})}
    with pytest.raises(SchemaMismatchError):
        write(sampled2, {"klanten": []}, ["klanten"], db)

"""ID-offset, FK-rewrite, NaN passthrough, sheet-name limits, sheet ordering."""

from __future__ import annotations

import pandas as pd
import pytest

from fk_resolver import ForeignKey
from xlsx_writer import OutputExistsError, TableNameTooLongError, write


def test_id_offset_new_file(tmp_path):
    out = str(tmp_path / "out.xlsx")
    sampled = {
        "klanten": pd.DataFrame({"id": [10, 20], "naam": ["A", "B"]}),
    }
    id_map = write(sampled, {"klanten": []}, ["klanten"], out)

    assert id_map["klanten"] == {10: 1, 20: 2}

    sheets = pd.read_excel(out, sheet_name=None)
    assert list(sheets["klanten"]["id"]) == [1, 2]
    assert list(sheets["klanten"]["naam"]) == ["A", "B"]


def test_fk_rewrite_consistent(tmp_path):
    out = str(tmp_path / "out.xlsx")
    sampled = {
        "klanten": pd.DataFrame({"id": [10, 20], "naam": ["A", "B"]}),
        "orders": pd.DataFrame({"id": [100, 101], "klant_id": [10, 20]}),
    }
    fks = {
        "klanten": [],
        "orders": [ForeignKey("klant_id", "klanten", "id")],
    }

    id_map = write(sampled, fks, ["klanten", "orders"], out)

    assert id_map["klanten"] == {10: 1, 20: 2}
    assert id_map["orders"] == {100: 1, 101: 2}

    sheets = pd.read_excel(out, sheet_name=None)
    rows = list(zip(sheets["orders"]["id"], sheets["orders"]["klant_id"]))
    assert rows == [(1, 1), (2, 2)]


def test_nan_passthrough(tmp_path):
    out = str(tmp_path / "out.xlsx")
    sampled = {
        "klanten": pd.DataFrame({"id": [1, 2], "naam": ["A", None]}),
    }
    write(sampled, {"klanten": []}, ["klanten"], out)

    df = pd.read_excel(out, sheet_name="klanten")
    assert df.iloc[0]["naam"] == "A"
    assert pd.isna(df.iloc[1]["naam"])


def test_empty_table_writes_headers_only(tmp_path):
    out = str(tmp_path / "out.xlsx")
    sampled = {
        "klanten": pd.DataFrame({"id": [], "naam": []}),
    }
    id_map = write(sampled, {"klanten": []}, ["klanten"], out)

    assert id_map["klanten"] == {}

    df = pd.read_excel(out, sheet_name="klanten")
    assert list(df.columns) == ["id", "naam"]
    assert len(df) == 0


def test_table_name_too_long_fails(tmp_path):
    out = str(tmp_path / "out.xlsx")
    long_name = "a" * 32
    sampled = {long_name: pd.DataFrame({"id": [1]})}

    with pytest.raises(TableNameTooLongError):
        write(sampled, {long_name: []}, [long_name], out)


def test_topological_sheet_order(tmp_path):
    out = str(tmp_path / "out.xlsx")
    sampled = {
        "klanten": pd.DataFrame({"id": [1], "naam": ["A"]}),
        "orders": pd.DataFrame({"id": [1], "klant_id": [1]}),
        "orderlines": pd.DataFrame({"id": [1], "order_id": [1]}),
    }
    fks = {
        "klanten": [],
        "orders": [ForeignKey("klant_id", "klanten", "id")],
        "orderlines": [ForeignKey("order_id", "orders", "id")],
    }
    topo = ["klanten", "orders", "orderlines"]

    write(sampled, fks, topo, out)

    sheets = pd.read_excel(out, sheet_name=None)
    assert list(sheets.keys()) == topo


def test_output_exists_fails(tmp_path):
    out = tmp_path / "out.xlsx"
    out.write_text("dummy")

    sampled = {"klanten": pd.DataFrame({"id": [1]})}
    with pytest.raises(OutputExistsError):
        write(sampled, {"klanten": []}, ["klanten"], str(out))

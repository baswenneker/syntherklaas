"""Writer round-trip tests for csv-loose, xlsx-loose, xlsx-multi, sqlite."""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from writers import WriterError, write
from xlsx_writer import (
    OutputExistsError,
    RowLimitExceededError,
    TableNameTooLongError,
)


@pytest.fixture
def small_tables():
    users = pd.DataFrame({"id": [1, 2, 3], "naam": ["A", "B", "C"]})
    events = pd.DataFrame({"id": [1, 2], "user_id": [1, 2], "kind": ["click", "view"]})
    return {"users": users, "events": events}, ["users", "events"]


# -- csv-loose ------------------------------------------------------------


def test_csv_loose_writes_one_per_table(tmp_path, small_tables):
    tables, topo = small_tables
    out_dir = tmp_path / "csv_out"
    write(tables, topo, str(out_dir), "csv-loose")
    assert (out_dir / "users.csv").exists()
    assert (out_dir / "events.csv").exists()
    back = pd.read_csv(out_dir / "users.csv")
    assert back["naam"].tolist() == ["A", "B", "C"]


def test_csv_loose_refuses_non_empty_dir(tmp_path, small_tables):
    tables, topo = small_tables
    out_dir = tmp_path / "csv_out"
    out_dir.mkdir()
    (out_dir / "existing.txt").write_text("hello")
    with pytest.raises(WriterError, match="not empty"):
        write(tables, topo, str(out_dir), "csv-loose")


# -- xlsx-loose -----------------------------------------------------------


def test_xlsx_loose_writes_one_per_table(tmp_path, small_tables):
    tables, topo = small_tables
    out_dir = tmp_path / "xlsx_out"
    write(tables, topo, str(out_dir), "xlsx-loose")
    assert (out_dir / "users.xlsx").exists()
    assert (out_dir / "events.xlsx").exists()
    back = pd.read_excel(out_dir / "users.xlsx")
    assert back["naam"].tolist() == ["A", "B", "C"]


# -- xlsx-multi -----------------------------------------------------------


def test_xlsx_multi_single_file_with_sheets(tmp_path, small_tables):
    tables, topo = small_tables
    out = tmp_path / "multi.xlsx"
    write(tables, topo, str(out), "xlsx-multi")
    assert out.exists()
    sheets = pd.read_excel(out, sheet_name=None)
    assert set(sheets) == {"users", "events"}
    assert sheets["events"]["kind"].tolist() == ["click", "view"]


def test_xlsx_multi_refuses_existing_file(tmp_path, small_tables):
    tables, topo = small_tables
    out = tmp_path / "multi.xlsx"
    out.write_text("already here")
    with pytest.raises(OutputExistsError):
        write(tables, topo, str(out), "xlsx-multi")


def test_xlsx_multi_rejects_long_table_names(tmp_path):
    long_name = "x" * 32
    tables = {long_name: pd.DataFrame({"id": [1]})}
    out = tmp_path / "multi.xlsx"
    with pytest.raises(TableNameTooLongError):
        write(tables, [long_name], str(out), "xlsx-multi")


# -- sqlite ---------------------------------------------------------------


def test_sqlite_roundtrip(tmp_path, small_tables):
    tables, topo = small_tables
    out = tmp_path / "out.sqlite"
    write(tables, topo, str(out), "sqlite")
    assert out.exists()
    with sqlite3.connect(str(out)) as conn:
        rows = conn.execute("SELECT id, naam FROM users ORDER BY id").fetchall()
    assert rows == [(1, "A"), (2, "B"), (3, "C")]


def test_sqlite_refuses_existing(tmp_path, small_tables):
    tables, topo = small_tables
    out = tmp_path / "out.sqlite"
    out.write_text("already here")
    with pytest.raises(WriterError, match="already exists"):
        write(tables, topo, str(out), "sqlite")


# -- unsupported format ---------------------------------------------------


def test_unsupported_format(tmp_path, small_tables):
    tables, topo = small_tables
    with pytest.raises(WriterError, match="Unsupported format"):
        write(tables, topo, str(tmp_path / "x"), "parquet")


# -- excel row limit ------------------------------------------------------


def test_xlsx_multi_row_limit_check(tmp_path):
    """Synthesize a tiny over-limit to confirm the check fires.

    We don't actually build 1M rows in the test; instead we monkey-check by
    constructing a DataFrame with a single row but assert the validator's
    error type for table-name too long (proxied above). Row-limit path is
    exercised by hitting a low test threshold via monkeypatch.
    """
    import xlsx_writer

    saved = xlsx_writer.EXCEL_ROW_LIMIT
    try:
        xlsx_writer.EXCEL_ROW_LIMIT = 1
        tables = {"big": pd.DataFrame({"id": [1, 2, 3]})}
        out = tmp_path / "big.xlsx"
        with pytest.raises(RowLimitExceededError):
            write(tables, ["big"], str(out), "xlsx-multi")
    finally:
        xlsx_writer.EXCEL_ROW_LIMIT = saved

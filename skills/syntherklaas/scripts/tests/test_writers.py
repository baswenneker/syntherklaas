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


# -- postgres / mssql SQL writer -----------------------------------------

from datetime import datetime  # noqa: E402


@pytest.fixture
def sql_fixtures():
    users = pd.DataFrame({"id": [1, 2, 3], "naam": ["A", "B", "C"]})
    events = pd.DataFrame(
        {"id": [1, 2], "user_id": [1, 2], "kind": ["click", "view"]}
    )
    schema_tables = [
        {
            "name": "users",
            "columns": [
                {"name": "id", "provider": "sequential", "primary_key": True},
                {"name": "naam", "provider": "faker.name", "unique": True},
            ],
        },
        {
            "name": "events",
            "columns": [
                {"name": "id", "provider": "sequential", "primary_key": True},
                {"name": "user_id", "provider": "fk", "references": "users.id"},
                {"name": "kind", "provider": "categorical"},
            ],
        },
    ]
    return {"users": users, "events": events}, ["users", "events"], schema_tables


DIALECT_QUOTES = {
    "postgres": {
        "users_ident": '"users"',
        "naam_ident": '"naam"',
        "id_ident": '"id"',
        "fk_reference": 'REFERENCES "users"("id")',
        "string_prefix": "'",
        "tx_begin": "BEGIN;",
    },
    "mssql": {
        "users_ident": "[users]",
        "naam_ident": "[naam]",
        "id_ident": "[id]",
        "fk_reference": "REFERENCES [users]([id])",
        "string_prefix": "N'",
        "tx_begin": "BEGIN TRANSACTION;",
    },
}


@pytest.mark.parametrize("dialect", ["postgres", "mssql"])
def test_sql_writes_single_file(tmp_path, sql_fixtures, dialect):
    tables, topo, schema = sql_fixtures
    out = tmp_path / f"out.{dialect}.sql"
    write(tables, topo, str(out), dialect, schema_tables=schema)
    assert out.exists()
    assert out.suffix == ".sql"


@pytest.mark.parametrize("dialect", ["postgres", "mssql"])
def test_sql_refuses_existing_file(tmp_path, sql_fixtures, dialect):
    tables, topo, schema = sql_fixtures
    out = tmp_path / "out.sql"
    out.write_text("already here")
    with pytest.raises(WriterError, match="already exists"):
        write(tables, topo, str(out), dialect, schema_tables=schema)


@pytest.mark.parametrize("dialect", ["postgres", "mssql"])
def test_sql_create_table_quoting(tmp_path, sql_fixtures, dialect):
    tables, topo, schema = sql_fixtures
    out = tmp_path / "out.sql"
    write(tables, topo, str(out), dialect, schema_tables=schema)
    text = out.read_text()
    q = DIALECT_QUOTES[dialect]
    assert f"CREATE TABLE {q['users_ident']}" in text
    assert q["naam_ident"] in text


@pytest.mark.parametrize("dialect", ["postgres", "mssql"])
def test_sql_pk_constraint_emitted(tmp_path, sql_fixtures, dialect):
    tables, topo, schema = sql_fixtures
    out = tmp_path / "out.sql"
    write(tables, topo, str(out), dialect, schema_tables=schema)
    text = out.read_text()
    q = DIALECT_QUOTES[dialect]
    # The id column line should contain PRIMARY KEY
    id_lines = [line for line in text.splitlines() if q["id_ident"] in line and "PRIMARY KEY" in line]
    assert id_lines, f"No PRIMARY KEY on id column found in:\n{text}"


@pytest.mark.parametrize("dialect", ["postgres", "mssql"])
def test_sql_unique_constraint_emitted(tmp_path, sql_fixtures, dialect):
    tables, topo, schema = sql_fixtures
    out = tmp_path / "out.sql"
    write(tables, topo, str(out), dialect, schema_tables=schema)
    text = out.read_text()
    q = DIALECT_QUOTES[dialect]
    unique_lines = [line for line in text.splitlines() if q["naam_ident"] in line and "UNIQUE" in line]
    assert unique_lines, f"No UNIQUE on naam column found in:\n{text}"


@pytest.mark.parametrize("dialect", ["postgres", "mssql"])
def test_sql_fk_reference_emitted(tmp_path, sql_fixtures, dialect):
    tables, topo, schema = sql_fixtures
    out = tmp_path / "out.sql"
    write(tables, topo, str(out), dialect, schema_tables=schema)
    text = out.read_text()
    assert DIALECT_QUOTES[dialect]["fk_reference"] in text
    assert "CASCADE" not in text


@pytest.mark.parametrize("dialect", ["postgres", "mssql"])
def test_sql_string_escaping(tmp_path, dialect):
    tables = {"t": pd.DataFrame({"id": [1], "naam": ["O'Brien"]})}
    schema = [
        {
            "name": "t",
            "columns": [
                {"name": "id", "provider": "sequential", "primary_key": True},
                {"name": "naam", "provider": "faker.name"},
            ],
        }
    ]
    out = tmp_path / "out.sql"
    write(tables, ["t"], str(out), dialect, schema_tables=schema)
    text = out.read_text()
    # Quote is doubled
    assert "O''Brien" in text
    # MSSQL prefixes string literals with N'; Postgres does not
    if dialect == "mssql":
        assert "N'O''Brien'" in text
    else:
        assert "'O''Brien'" in text
        assert "N'O''Brien'" not in text


@pytest.mark.parametrize("dialect", ["postgres", "mssql"])
def test_sql_null_for_missing(tmp_path, dialect):
    tables = {"t": pd.DataFrame({"id": [1, 2], "naam": ["A", None]})}
    schema = [
        {
            "name": "t",
            "columns": [
                {"name": "id", "provider": "sequential", "primary_key": True},
                {"name": "naam", "provider": "faker.name"},
            ],
        }
    ]
    out = tmp_path / "out.sql"
    write(tables, ["t"], str(out), dialect, schema_tables=schema)
    text = out.read_text()
    # Bare NULL keyword (no quotes); the value should land as "NULL"
    assert "NULL)" in text or "NULL," in text


@pytest.mark.parametrize("dialect", ["postgres", "mssql"])
def test_sql_datetime_iso_quoted(tmp_path, dialect):
    tables = {
        "t": pd.DataFrame(
            {"id": [1], "ts": [datetime(2026, 5, 14, 12, 30, 0)]}
        )
    }
    schema = [
        {
            "name": "t",
            "columns": [
                {"name": "id", "provider": "sequential", "primary_key": True},
                {"name": "ts", "provider": "datetime_range"},
            ],
        }
    ]
    out = tmp_path / "out.sql"
    write(tables, ["t"], str(out), dialect, schema_tables=schema)
    text = out.read_text()
    assert "2026-05-14 12:30:00" in text


@pytest.mark.parametrize("dialect", ["postgres", "mssql"])
def test_sql_batching_splits_at_1000(tmp_path, dialect):
    n_rows = 2500
    tables = {
        "t": pd.DataFrame({"id": list(range(1, n_rows + 1)), "naam": ["x"] * n_rows})
    }
    schema = [
        {
            "name": "t",
            "columns": [
                {"name": "id", "provider": "sequential", "primary_key": True},
                {"name": "naam", "provider": "faker.name"},
            ],
        }
    ]
    out = tmp_path / "out.sql"
    write(tables, ["t"], str(out), dialect, schema_tables=schema)
    text = out.read_text()
    # 2500 rows / 1000 batch → 3 INSERT statements
    assert text.count("INSERT INTO") == 3


@pytest.mark.parametrize("dialect", ["postgres", "mssql"])
def test_sql_topo_order_respected(tmp_path, sql_fixtures, dialect):
    tables, topo, schema = sql_fixtures
    out = tmp_path / "out.sql"
    write(tables, topo, str(out), dialect, schema_tables=schema)
    text = out.read_text()
    users_ident = DIALECT_QUOTES[dialect]["users_ident"]
    events_ident = users_ident.replace("users", "events")
    users_pos = text.find(f"CREATE TABLE {users_ident}")
    events_pos = text.find(f"CREATE TABLE {events_ident}")
    assert users_pos != -1
    assert events_pos != -1
    assert users_pos < events_pos


@pytest.mark.parametrize("dialect", ["postgres", "mssql"])
def test_sql_transaction_wraps_output(tmp_path, sql_fixtures, dialect):
    tables, topo, schema = sql_fixtures
    out = tmp_path / "out.sql"
    write(tables, topo, str(out), dialect, schema_tables=schema)
    lines = [l for l in out.read_text().splitlines() if l.strip() and not l.startswith("--")]
    assert lines[0] == DIALECT_QUOTES[dialect]["tx_begin"]
    assert lines[-1] == "COMMIT;"

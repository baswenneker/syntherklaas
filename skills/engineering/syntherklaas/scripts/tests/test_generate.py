"""End-to-end: schema -> generated DataFrames + FK integrity + determinism."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from fk_resolver import CyclicForeignKeyError
from generate import _build_topo, _generate_tables
from providers import Generator
from schema import validate

SCRIPTS_DIR = Path(__file__).resolve().parent.parent


def _gen(schema):
    validate(schema)
    topo = _build_topo(schema)
    g = Generator(locale=schema["locale"], seed=schema["seed"])
    return _generate_tables(schema, topo, g), topo


# -- row counts -----------------------------------------------------------


def test_root_count_fixed(minimal_schema):
    tables, _ = _gen(minimal_schema)
    assert len(tables["users"]) == 10


def test_per_parent_fixed(minimal_schema):
    tables, _ = _gen(minimal_schema)
    # 10 users × 3 events each = 30
    assert len(tables["events"]) == 30


def test_root_columns_preserved(minimal_schema):
    tables, _ = _gen(minimal_schema)
    assert list(tables["users"].columns) == ["id", "naam", "bsn"]
    assert list(tables["events"].columns) == ["id", "user_id", "kind"]


def test_sequential_ids_are_1_based(minimal_schema):
    tables, _ = _gen(minimal_schema)
    assert tables["users"]["id"].tolist() == list(range(1, 11))
    assert tables["events"]["id"].tolist() == list(range(1, 31))


# -- FK integrity ---------------------------------------------------------


def test_fk_values_subset_of_parent_ids(minimal_schema):
    tables, _ = _gen(minimal_schema)
    parent_ids = set(tables["users"]["id"].tolist())
    child_fks = set(tables["events"]["user_id"].tolist())
    assert child_fks.issubset(parent_ids)


def test_per_parent_each_parent_has_exactly_k_children(minimal_schema):
    tables, _ = _gen(minimal_schema)
    counts = tables["events"]["user_id"].value_counts().to_dict()
    # Every user should appear exactly 3 times since distribution=fixed value=3
    assert all(c == 3 for c in counts.values())
    assert set(counts.keys()) == set(tables["users"]["id"].tolist())


# -- determinism ----------------------------------------------------------


def test_same_schema_identical_output(minimal_schema):
    a, _ = _gen(minimal_schema)
    b, _ = _gen(minimal_schema)
    for name in a:
        assert a[name].equals(b[name])


def test_different_seed_different_output(minimal_schema):
    schema_a = {**minimal_schema, "seed": 1}
    schema_b = {**minimal_schema, "seed": 2}
    a, _ = _gen(schema_a)
    b, _ = _gen(schema_b)
    # Names will differ between two random seeds
    assert a["users"]["naam"].tolist() != b["users"]["naam"].tolist()


# -- cyclic FK ------------------------------------------------------------


def test_cyclic_fk_raises():
    schema = {
        "version": 1,
        "locale": "nl_NL",
        "tables": [
            {
                "name": "a",
                "columns": [
                    {"name": "id", "provider": "sequential"},
                    {"name": "b_id", "provider": "fk", "references": "b.id"},
                ],
                "volume": {"count": {"distribution": "fixed", "value": 1}},
            },
            {
                "name": "b",
                "columns": [
                    {"name": "id", "provider": "sequential"},
                    {"name": "a_id", "provider": "fk", "references": "a.id"},
                ],
                "volume": {"count": {"distribution": "fixed", "value": 1}},
            },
        ],
    }
    validate(schema)
    with pytest.raises(CyclicForeignKeyError):
        _build_topo(schema)


# -- CLI integration -----------------------------------------------------


@pytest.fixture
def schema_yaml_path(tmp_path, minimal_schema):
    p = tmp_path / "schema.yaml"
    p.write_text(yaml.safe_dump(minimal_schema))
    return p


def _run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "generate.py"), *args],
        capture_output=True,
        text=True,
    )


def test_cli_preview_emits_json(schema_yaml_path):
    result = _run_cli("--schema", str(schema_yaml_path), "--preview")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert set(data.keys()) == {"users", "events"}
    assert data["users"]["row_count_total"] == 10
    assert len(data["users"]["rows"]) == 10


def test_cli_writes_sqlite(tmp_path, schema_yaml_path):
    out = tmp_path / "out.sqlite"
    result = _run_cli(
        "--schema", str(schema_yaml_path),
        "--output", str(out),
        "--format", "sqlite",
    )
    assert result.returncode == 0, result.stderr
    assert out.exists()


def test_cli_bad_schema_exits_2(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("version: 1\ntables: []\n")
    result = _run_cli("--schema", str(bad), "--preview")
    assert result.returncode == 2
    assert "Schema error" in result.stderr


def test_cli_uses_output_block_from_schema(tmp_path, minimal_schema):
    out = tmp_path / "out.sqlite"
    minimal_schema["output"] = {"format": "sqlite", "path": str(out)}
    p = tmp_path / "schema.yaml"
    p.write_text(yaml.safe_dump(minimal_schema))
    result = _run_cli("--schema", str(p))
    assert result.returncode == 0, result.stderr
    assert out.exists()

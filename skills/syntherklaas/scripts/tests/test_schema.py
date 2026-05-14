"""Schema YAML validator tests."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from schema import SchemaError, load_schema, validate


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "schema.yaml"
    p.write_text(textwrap.dedent(body))
    return p


# -- happy paths ----------------------------------------------------------


def test_valid_schema_loads(minimal_schema):
    validate(minimal_schema)  # should not raise


def test_load_from_yaml_file(tmp_path):
    p = _write(
        tmp_path,
        """
        version: 1
        tables:
          - name: users
            columns:
              - { name: id, provider: sequential }
              - { name: naam, provider: faker.name }
            volume: { count: { distribution: fixed, value: 5 } }
        """,
    )
    schema = load_schema(p)
    assert schema["locale"] == "nl_NL"
    assert len(schema["tables"]) == 1


def test_load_resolves_default_locale(tmp_path):
    p = _write(
        tmp_path,
        """
        version: 1
        tables:
          - name: a
            columns: [{ name: id, provider: sequential }]
            volume: { count: { distribution: fixed, value: 1 } }
        """,
    )
    schema = load_schema(p)
    assert schema["locale"] == "nl_NL"


# -- version --------------------------------------------------------------


def test_missing_version_rejected(minimal_schema):
    del minimal_schema["version"]
    with pytest.raises(SchemaError, match="version"):
        validate(minimal_schema)


def test_wrong_version_rejected(minimal_schema):
    minimal_schema["version"] = 99
    with pytest.raises(SchemaError, match="version"):
        validate(minimal_schema)


# -- tables ---------------------------------------------------------------


def test_empty_tables_rejected():
    with pytest.raises(SchemaError, match="tables"):
        validate({"version": 1, "tables": []})


def test_duplicate_column_rejected(minimal_schema):
    minimal_schema["tables"][0]["columns"].append(
        {"name": "naam", "provider": "faker.name"}
    )
    with pytest.raises(SchemaError, match="duplicate column"):
        validate(minimal_schema)


# -- providers ------------------------------------------------------------


def test_unknown_provider_rejected(minimal_schema):
    minimal_schema["tables"][0]["columns"][1]["provider"] = "doesnotexist"
    with pytest.raises(SchemaError, match="unknown provider"):
        validate(minimal_schema)


def test_unknown_faker_method_rejected(minimal_schema):
    minimal_schema["tables"][0]["columns"][1]["provider"] = "faker.zzzz_not_a_thing"
    with pytest.raises(SchemaError, match="unknown faker method"):
        validate(minimal_schema)


# -- FK refs --------------------------------------------------------------


def test_fk_to_unknown_table(minimal_schema):
    minimal_schema["tables"][1]["columns"][1]["references"] = "ghost.id"
    with pytest.raises(SchemaError, match="unknown table"):
        validate(minimal_schema)


def test_fk_to_unknown_column(minimal_schema):
    minimal_schema["tables"][1]["columns"][1]["references"] = "users.ghost"
    with pytest.raises(SchemaError, match="unknown column"):
        validate(minimal_schema)


def test_fk_without_references_rejected(minimal_schema):
    minimal_schema["tables"][1]["columns"][1].pop("references")
    with pytest.raises(SchemaError, match="references"):
        validate(minimal_schema)


# -- categorical ----------------------------------------------------------


def test_categorical_without_choices_rejected(minimal_schema):
    minimal_schema["tables"][1]["columns"][2].pop("choices")
    with pytest.raises(SchemaError, match="choices"):
        validate(minimal_schema)


def test_categorical_weights_mismatch_rejected(minimal_schema):
    minimal_schema["tables"][1]["columns"][2]["weights"] = [0.5]
    with pytest.raises(SchemaError, match="weights"):
        validate(minimal_schema)


# -- numeric_range --------------------------------------------------------


def test_numeric_range_uniform_requires_min_max():
    schema = {
        "version": 1,
        "tables": [
            {
                "name": "a",
                "columns": [
                    {"name": "id", "provider": "sequential"},
                    {"name": "n", "provider": "numeric_range", "type": "int"},
                ],
                "volume": {"count": {"distribution": "fixed", "value": 1}},
            }
        ],
    }
    with pytest.raises(SchemaError, match="min"):
        validate(schema)


def test_numeric_range_normal_requires_mean_stddev():
    schema = {
        "version": 1,
        "tables": [
            {
                "name": "a",
                "columns": [
                    {"name": "id", "provider": "sequential"},
                    {
                        "name": "x",
                        "provider": "numeric_range",
                        "distribution": "normal",
                        "min": 0,
                        "max": 1,
                    },
                ],
                "volume": {"count": {"distribution": "fixed", "value": 1}},
            }
        ],
    }
    with pytest.raises(SchemaError, match="mean"):
        validate(schema)


# -- volume ---------------------------------------------------------------


def test_both_count_and_per_parent_rejected(minimal_schema):
    minimal_schema["tables"][1]["volume"]["count"] = {"distribution": "fixed", "value": 1}
    with pytest.raises(SchemaError, match="exactly one"):
        validate(minimal_schema)


def test_neither_count_nor_per_parent_rejected(minimal_schema):
    minimal_schema["tables"][0]["volume"] = {}
    with pytest.raises(SchemaError, match="exactly one"):
        validate(minimal_schema)


def test_per_parent_unknown_parent_rejected(minimal_schema):
    minimal_schema["tables"][1]["volume"]["per_parent"]["parent"] = "ghost"
    with pytest.raises(SchemaError, match="known table"):
        validate(minimal_schema)


def test_count_poisson_requires_lambda(minimal_schema):
    minimal_schema["tables"][0]["volume"] = {"count": {"distribution": "poisson"}}
    with pytest.raises(SchemaError, match="lambda"):
        validate(minimal_schema)


# -- output block ---------------------------------------------------------


def test_output_unknown_format_rejected(minimal_schema):
    minimal_schema["output"] = {"format": "json", "path": "./x.json"}
    with pytest.raises(SchemaError, match="format"):
        validate(minimal_schema)


def test_output_path_must_be_string(minimal_schema):
    minimal_schema["output"] = {"format": "sqlite", "path": 42}
    with pytest.raises(SchemaError, match="path"):
        validate(minimal_schema)


# -- conditional values (when) -------------------------------------------


def _schema_with_when(when_clause, *, target_provider="faker.url"):
    return {
        "version": 1,
        "tables": [
            {
                "name": "events",
                "columns": [
                    {"name": "id", "provider": "sequential"},
                    {
                        "name": "event_type",
                        "provider": "categorical",
                        "choices": ["click", "open"],
                    },
                    {"name": "url", "provider": target_provider, "when": when_clause},
                ],
                "volume": {"count": {"distribution": "fixed", "value": 1}},
            }
        ],
    }


def test_when_happy_path():
    validate(_schema_with_when({"column": "event_type", "equals": "click"}))


def test_when_accepts_list_equals():
    validate(_schema_with_when({"column": "event_type", "equals": ["click", "open"]}))


def test_when_unknown_column_rejected():
    with pytest.raises(SchemaError, match="defined earlier"):
        validate(_schema_with_when({"column": "ghost", "equals": "click"}))


def test_when_forward_reference_rejected():
    # `when.column` points to a column defined AFTER the conditional column
    schema = {
        "version": 1,
        "tables": [
            {
                "name": "events",
                "columns": [
                    {"name": "id", "provider": "sequential"},
                    {
                        "name": "url",
                        "provider": "faker.url",
                        "when": {"column": "event_type", "equals": "click"},
                    },
                    {
                        "name": "event_type",
                        "provider": "categorical",
                        "choices": ["click", "open"],
                    },
                ],
                "volume": {"count": {"distribution": "fixed", "value": 1}},
            }
        ],
    }
    with pytest.raises(SchemaError, match="defined earlier"):
        validate(schema)


def test_when_self_reference_rejected():
    with pytest.raises(SchemaError, match="itself"):
        validate(_schema_with_when({"column": "url", "equals": "click"}))


def test_when_on_sequential_rejected():
    schema = {
        "version": 1,
        "tables": [
            {
                "name": "t",
                "columns": [
                    {"name": "kind", "provider": "categorical", "choices": ["a", "b"]},
                    {
                        "name": "id",
                        "provider": "sequential",
                        "when": {"column": "kind", "equals": "a"},
                    },
                ],
                "volume": {"count": {"distribution": "fixed", "value": 1}},
            }
        ],
    }
    with pytest.raises(SchemaError, match="not allowed"):
        validate(schema)


def test_when_on_fk_rejected(minimal_schema):
    minimal_schema["tables"][1]["columns"][1]["when"] = {
        "column": "id",
        "equals": 1,
    }
    with pytest.raises(SchemaError, match="not allowed"):
        validate(minimal_schema)


def test_when_missing_equals_rejected():
    with pytest.raises(SchemaError, match="equals"):
        validate(_schema_with_when({"column": "event_type"}))


def test_when_empty_list_equals_rejected():
    with pytest.raises(SchemaError, match="non-empty"):
        validate(_schema_with_when({"column": "event_type", "equals": []}))


# -- file IO --------------------------------------------------------------


def test_missing_file_raises(tmp_path):
    with pytest.raises(SchemaError, match="not found"):
        load_schema(tmp_path / "nope.yaml")


def test_malformed_yaml_raises(tmp_path):
    p = tmp_path / "schema.yaml"
    p.write_text(":\n: bad\n")
    with pytest.raises(SchemaError, match="YAML"):
        load_schema(p)

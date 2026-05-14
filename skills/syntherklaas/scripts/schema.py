"""Schema-YAML loader and validator for syntherklaas.

Accepts a path to a YAML file, returns a fully-validated schema dict. On
failure raises ``SchemaError``; the CLI translates that to exit code 2.

Validates structure, provider names + per-provider required params, FK targets,
volume + distribution shapes. Does not load Faker or numpy — pure schema check.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import yaml

from providers import (
    COUNT_DISTRIBUTIONS,
    DATETIME_DISTRIBUTIONS,
    NATIVE_PROVIDERS,
    NL_PROVIDERS,
    NUMERIC_DISTRIBUTIONS,
    is_faker_method,
)

SCHEMA_VERSION = 1
ALLOWED_FORMATS = frozenset({"csv-loose", "xlsx-loose", "xlsx-multi", "sqlite"})


class SchemaError(ValueError):
    """Raised for any schema validation failure. CLI maps to exit 2."""


@dataclass
class FKRef:
    table: str
    column: str


def load_schema(path: str | Path) -> Dict[str, Any]:
    """Load + validate a schema-YAML; return the validated dict."""
    p = Path(path)
    if not p.exists():
        raise SchemaError(f"Schema file not found: {path}")
    try:
        raw = yaml.safe_load(p.read_text())
    except yaml.YAMLError as e:
        raise SchemaError(f"Invalid YAML: {e}") from e
    if not isinstance(raw, dict):
        raise SchemaError("Top-level YAML must be a mapping")
    return validate(raw)


def validate(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a parsed schema dict in-place; return it. Raise SchemaError on issues."""
    _require_version(schema)
    schema.setdefault("locale", "nl_NL")
    _check_type(schema, "locale", str)
    if "seed" in schema:
        _check_type(schema, "seed", int)
    if "output" in schema:
        _validate_output(schema["output"])

    tables = schema.get("tables")
    if not isinstance(tables, list) or not tables:
        raise SchemaError("'tables' must be a non-empty list")

    table_columns: Dict[str, List[str]] = {}
    for tbl in tables:
        _validate_table_shape(tbl)
        table_columns[tbl["name"]] = [c["name"] for c in tbl["columns"]]

    # Now that we know all tables/columns, validate cross-table refs.
    for tbl in tables:
        for col in tbl["columns"]:
            if col["provider"] == "fk":
                _validate_fk_ref(col, tbl["name"], table_columns)
        _validate_volume(tbl, table_columns)

    return schema


# -- top-level helpers ----------------------------------------------------


def _require_version(schema: Dict[str, Any]) -> None:
    version = schema.get("version")
    if version is None:
        raise SchemaError("'version' is required at top level")
    if version != SCHEMA_VERSION:
        raise SchemaError(
            f"Unsupported schema version {version!r}; expected {SCHEMA_VERSION}"
        )


def _validate_output(output: Any) -> None:
    if not isinstance(output, dict):
        raise SchemaError("'output' must be a mapping with 'format' and 'path'")
    fmt = output.get("format")
    if fmt not in ALLOWED_FORMATS:
        raise SchemaError(
            f"output.format must be one of {sorted(ALLOWED_FORMATS)}; got {fmt!r}"
        )
    if not isinstance(output.get("path"), str):
        raise SchemaError("output.path must be a string")


# -- table validation -----------------------------------------------------


def _validate_table_shape(tbl: Any) -> None:
    if not isinstance(tbl, dict):
        raise SchemaError("Each table must be a mapping")
    name = tbl.get("name")
    if not isinstance(name, str) or not name:
        raise SchemaError("Each table needs a non-empty 'name'")
    cols = tbl.get("columns")
    if not isinstance(cols, list) or not cols:
        raise SchemaError(f"Table {name!r}: 'columns' must be a non-empty list")
    if "volume" not in tbl or not isinstance(tbl["volume"], dict):
        raise SchemaError(f"Table {name!r}: 'volume' (mapping) is required")
    seen_cols: set[str] = set()
    for col in cols:
        _validate_column(col, name)
        if "when" in col:
            _validate_when(col, name, seen_cols)
        if col["name"] in seen_cols:
            raise SchemaError(f"Table {name!r}: duplicate column {col['name']!r}")
        seen_cols.add(col["name"])


# -- column validation ----------------------------------------------------


def _validate_column(col: Any, table_name: str) -> None:
    if not isinstance(col, dict):
        raise SchemaError(f"Table {table_name!r}: every column must be a mapping")
    name = col.get("name")
    if not isinstance(name, str) or not name:
        raise SchemaError(f"Table {table_name!r}: column without a 'name'")
    provider = col.get("provider")
    if not isinstance(provider, str):
        raise SchemaError(f"{table_name}.{name}: 'provider' is required")

    if provider in NATIVE_PROVIDERS:
        _validate_native_provider(col, table_name)
    elif provider in NL_PROVIDERS:
        pass  # no extra params required for NL providers
    elif provider.startswith("faker."):
        if not is_faker_method(provider):
            raise SchemaError(
                f"{table_name}.{name}: unknown faker method {provider!r}"
            )
    else:
        raise SchemaError(f"{table_name}.{name}: unknown provider {provider!r}")


def _validate_native_provider(col: Dict[str, Any], table_name: str) -> None:
    name = col["name"]
    provider = col["provider"]

    if provider == "sequential":
        return  # no extra params

    if provider == "fk":
        ref = col.get("references")
        if not isinstance(ref, str) or "." not in ref:
            raise SchemaError(
                f"{table_name}.{name}: fk requires 'references: <table>.<column>'"
            )
        return

    if provider == "categorical":
        choices = col.get("choices")
        if not isinstance(choices, list) or not choices:
            raise SchemaError(
                f"{table_name}.{name}: categorical requires a non-empty 'choices' list"
            )
        weights = col.get("weights")
        if weights is not None:
            if not isinstance(weights, list) or len(weights) != len(choices):
                raise SchemaError(
                    f"{table_name}.{name}: categorical 'weights' must match 'choices' length"
                )
            if any(not isinstance(w, (int, float)) or w < 0 for w in weights):
                raise SchemaError(
                    f"{table_name}.{name}: weights must be non-negative numbers"
                )
        return

    if provider == "numeric_range":
        _validate_numeric_range(col, table_name)
        return

    if provider == "datetime_range":
        _validate_datetime_range(col, table_name)
        return

    raise SchemaError(f"{table_name}.{name}: provider {provider!r} unhandled")


def _validate_numeric_range(col: Dict[str, Any], table_name: str) -> None:
    name = col["name"]
    dist = col.get("distribution", "uniform")
    if dist not in NUMERIC_DISTRIBUTIONS:
        raise SchemaError(
            f"{table_name}.{name}: numeric distribution {dist!r} not in {sorted(NUMERIC_DISTRIBUTIONS)}"
        )
    col_type = col.get("type", "float")
    if col_type not in ("int", "float"):
        raise SchemaError(f"{table_name}.{name}: numeric type must be 'int' or 'float'")

    if dist == "uniform":
        _require_keys(col, ("min", "max"), table_name)
    elif dist == "normal":
        _require_keys(col, ("mean", "stddev"), table_name)
    elif dist == "lognormal":
        if "sigma" not in col:
            raise SchemaError(f"{table_name}.{name}: lognormal requires 'sigma'")
    elif dist == "exponential":
        if "scale" not in col:
            raise SchemaError(f"{table_name}.{name}: exponential requires 'scale'")


def _validate_datetime_range(col: Dict[str, Any], table_name: str) -> None:
    name = col["name"]
    _require_keys(col, ("start", "end"), table_name)
    dist = col.get("distribution", "uniform")
    if dist not in DATETIME_DISTRIBUTIONS:
        raise SchemaError(
            f"{table_name}.{name}: datetime distribution {dist!r} not in {sorted(DATETIME_DISTRIBUTIONS)}"
        )


def _validate_when(
    col: Dict[str, Any],
    table_name: str,
    prior_cols: set[str],
) -> None:
    name = col["name"]
    provider = col["provider"]
    if provider in ("sequential", "fk") or col.get("primary_key"):
        raise SchemaError(
            f"{table_name}.{name}: 'when' is not allowed on {provider} or PK columns"
        )
    when = col["when"]
    if not isinstance(when, dict):
        raise SchemaError(f"{table_name}.{name}: 'when' must be a mapping")
    dep = when.get("column")
    if not isinstance(dep, str) or not dep:
        raise SchemaError(f"{table_name}.{name}: 'when.column' must be a non-empty string")
    if dep == name:
        raise SchemaError(f"{table_name}.{name}: 'when.column' cannot reference the column itself")
    if dep not in prior_cols:
        raise SchemaError(
            f"{table_name}.{name}: 'when.column' {dep!r} must be defined earlier in the same table"
        )
    if "equals" not in when:
        raise SchemaError(f"{table_name}.{name}: 'when' requires 'equals'")
    eq = when["equals"]
    if isinstance(eq, list) and not eq:
        raise SchemaError(f"{table_name}.{name}: 'when.equals' list must be non-empty")


def _validate_fk_ref(
    col: Dict[str, Any],
    table_name: str,
    table_columns: Dict[str, List[str]],
) -> None:
    ref = col["references"]
    parent_table, _, parent_col = ref.partition(".")
    if parent_table not in table_columns:
        raise SchemaError(
            f"{table_name}.{col['name']}: fk references unknown table {parent_table!r}"
        )
    if parent_col not in table_columns[parent_table]:
        raise SchemaError(
            f"{table_name}.{col['name']}: fk references unknown column "
            f"{parent_table}.{parent_col!r}"
        )


# -- volume validation ----------------------------------------------------


def _validate_volume(tbl: Dict[str, Any], table_columns: Dict[str, List[str]]) -> None:
    name = tbl["name"]
    volume = tbl["volume"]
    has_count = "count" in volume
    has_per_parent = "per_parent" in volume
    if has_count == has_per_parent:
        raise SchemaError(
            f"Table {name!r}: volume must have exactly one of 'count' or 'per_parent'"
        )

    spec = volume["count"] if has_count else volume["per_parent"]
    if not isinstance(spec, dict):
        raise SchemaError(f"Table {name!r}: volume spec must be a mapping")

    if has_per_parent:
        parent = spec.get("parent")
        if not isinstance(parent, str) or parent not in table_columns:
            raise SchemaError(
                f"Table {name!r}: per_parent.parent must reference a known table"
            )

    _validate_count_distribution(spec, name)


def _validate_count_distribution(spec: Dict[str, Any], table_name: str) -> None:
    dist = spec.get("distribution", "fixed")
    if dist not in COUNT_DISTRIBUTIONS:
        raise SchemaError(
            f"Table {table_name!r}: count distribution {dist!r} not in "
            f"{sorted(COUNT_DISTRIBUTIONS)}"
        )
    if dist == "fixed":
        _require_keys(spec, ("value",), table_name)
    elif dist == "uniform":
        _require_keys(spec, ("min", "max"), table_name)
    elif dist == "normal":
        _require_keys(spec, ("mean", "stddev"), table_name)
    elif dist == "poisson":
        _require_keys(spec, ("lambda",), table_name)


# -- shared helpers -------------------------------------------------------


def _check_type(d: Dict[str, Any], key: str, expected: type) -> None:
    if not isinstance(d[key], expected):
        raise SchemaError(f"'{key}' must be a {expected.__name__}; got {type(d[key]).__name__}")


def _require_keys(d: Dict[str, Any], keys: tuple, table_name: str) -> None:
    missing = [k for k in keys if k not in d]
    if missing:
        raise SchemaError(f"Table {table_name!r}: missing required keys {missing}")


# -- ancillary --------------------------------------------------------------


def list_tables(schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    return schema["tables"]


def fk_columns(table: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [c for c in table["columns"] if c["provider"] == "fk"]


def parse_fk(col: Dict[str, Any]) -> FKRef:
    parent_table, _, parent_col = col["references"].partition(".")
    return FKRef(table=parent_table, column=parent_col)

"""Shared pytest fixtures: scripts/ on sys.path + a minimal valid schema."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def minimal_schema():
    """Smallest valid schema: one root table, one child via per_parent."""
    return {
        "version": 1,
        "locale": "nl_NL",
        "seed": 42,
        "tables": [
            {
                "name": "users",
                "columns": [
                    {"name": "id", "provider": "sequential", "primary_key": True},
                    {"name": "naam", "provider": "faker.name"},
                    {"name": "bsn", "provider": "nl.bsn"},
                ],
                "volume": {"count": {"distribution": "fixed", "value": 10}},
            },
            {
                "name": "events",
                "columns": [
                    {"name": "id", "provider": "sequential", "primary_key": True},
                    {"name": "user_id", "provider": "fk", "references": "users.id"},
                    {
                        "name": "kind",
                        "provider": "categorical",
                        "choices": ["click", "view"],
                        "weights": [0.7, 0.3],
                    },
                ],
                "volume": {
                    "per_parent": {
                        "parent": "users",
                        "distribution": "fixed",
                        "value": 3,
                    }
                },
            },
        ],
    }

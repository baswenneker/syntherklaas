"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

# Make the scripts/ directory importable so tests can `import detector` etc.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def klanten_df():
    return pd.DataFrame(
        {
            "id": [1, 2, 3],
            "naam": ["Jan Jansen", "Anna de Vries", "Tim Bosch"],
            "email": ["jan@bedrijf.nl", "anna@firma.nl", "tim@klant.nl"],
        }
    )


@pytest.fixture
def orders_df():
    return pd.DataFrame(
        {
            "id": [101, 102, 103, 104, 105],
            "klant_id": [1, 1, 2, 2, 3],
            "datum": ["2024-01-01"] * 5,
        }
    )


@pytest.fixture
def orderlines_df():
    return pd.DataFrame(
        {
            "id": [1001, 1002, 1003, 1004],
            "order_id": [101, 101, 102, 103],
            "product": ["A", "B", "C", "D"],
        }
    )

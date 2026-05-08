"""CLI dispatcher pre-flight checks: extension, mode×format, identical paths."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
SCRIPT = SCRIPTS_DIR / "syntherklaas.py"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(SCRIPTS_DIR),
    )


def test_output_xlsx_exists_fails(tmp_path):
    inp = tmp_path / "in.xlsx"
    inp.write_text("dummy")
    out = tmp_path / "out.xlsx"
    out.write_text("dummy")

    result = _run_cli("--input", str(inp), "--output", str(out))

    assert result.returncode == 2
    assert "already exists" in result.stderr


def test_append_mode_xlsx_fails(tmp_path):
    inp = tmp_path / "in.xlsx"
    inp.write_text("dummy")
    out = tmp_path / "out.xlsx"

    result = _run_cli(
        "--input", str(inp),
        "--output", str(out),
        "--mode", "append",
    )

    assert result.returncode == 2
    assert "append" in result.stderr.lower()
    assert "xlsx" in result.stderr.lower()


def test_identical_paths_fails(tmp_path):
    same = tmp_path / "data.xlsx"
    same.write_text("dummy")

    result = _run_cli("--input", str(same), "--output", str(same))

    assert result.returncode == 2
    assert "identical" in result.stderr.lower()


def test_unsupported_extension_fails(tmp_path):
    inp = tmp_path / "in.xlsx"
    inp.write_text("dummy")
    out = tmp_path / "out.parquet"

    result = _run_cli("--input", str(inp), "--output", str(out))

    assert result.returncode == 2
    assert "unsupported output extension" in result.stderr.lower()

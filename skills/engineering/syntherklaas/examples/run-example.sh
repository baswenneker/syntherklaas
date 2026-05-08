#!/usr/bin/env bash
# End-to-end smoke test: generate sample → run pipeline (both output formats) → verify.
set -euo pipefail

EXAMPLES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${EXAMPLES_DIR}/.." && pwd)"
SCRIPTS_DIR="${SKILL_DIR}/scripts"
PROJECT_ROOT="$(cd "${SKILL_DIR}/../../.." && pwd)"

cd "${SCRIPTS_DIR}"

if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: uv not found. Install with:" >&2
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 4
fi

# First-run: sync deps + spacy model
INSTALL_MARKER=".venv/.syntherklaas-installed"
if [[ ! -f "${INSTALL_MARKER}" ]]; then
    echo ">>> Installing dependencies (first run)..."
    uv sync
    echo ">>> Downloading Spacy NL model (nl_core_news_md)..."
    uv run python -m spacy download nl_core_news_md
    mkdir -p "$(dirname "${INSTALL_MARKER}")"
    touch "${INSTALL_MARKER}"
    echo
fi

echo ">>> Generating sample input..."
uv run python "${EXAMPLES_DIR}/generate_sample.py"
echo

DB_OUT="/tmp/syntherklaas-demo.db"
XLSX_OUT="/tmp/syntherklaas-demo.xlsx"
rm -f "${DB_OUT}" "${XLSX_OUT}"

echo ">>> Pipeline 1/2: xlsx-input -> sqlite-output (${DB_OUT}, cap 50)"
uv run python syntherklaas.py \
    --input "${PROJECT_ROOT}/example_data/xlsx/example_data.xlsx" \
    --output "${DB_OUT}" \
    --max-rows 50

echo
echo ">>> Pipeline 2/2: csv-input -> xlsx-output (${XLSX_OUT}, cap 50)"
uv run python syntherklaas.py \
    --input "${PROJECT_ROOT}/example_data/csv" \
    --output "${XLSX_OUT}" \
    --max-rows 50

echo
echo ">>> Sanity check on ${DB_OUT} (sqlite3):"
uv run python - <<PY
import sqlite3
conn = sqlite3.connect("${DB_OUT}")
print(f"  klanten:    {conn.execute('SELECT COUNT(*) FROM klanten').fetchone()[0]} rows")
print(f"  orders:     {conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0]} rows")
print(f"  orderlines: {conn.execute('SELECT COUNT(*) FROM orderlines').fetchone()[0]} rows")
print()
print("  Top 5 klanten by order count (verifies FK joins work + names are anonymized):")
rows = conn.execute('''
    SELECT k.naam, COUNT(o.id) AS n_orders
    FROM klanten k LEFT JOIN orders o ON o.klant_id = k.id
    GROUP BY k.id ORDER BY n_orders DESC LIMIT 5
''').fetchall()
for naam, n in rows:
    print(f"    {naam!r}: {n} orders")
PY

echo
echo ">>> Sanity check on ${XLSX_OUT} (pandas readback):"
uv run python - <<PY
import pandas as pd
sheets = pd.read_excel("${XLSX_OUT}", sheet_name=None)
print(f"  klanten:    {len(sheets['klanten'])} rows")
print(f"  orders:     {len(sheets['orders'])} rows")
print(f"  orderlines: {len(sheets['orderlines'])} rows")
print()
print("  Top 5 klanten by order count (verifies FK joins work + names are anonymized):")
top = (
    sheets["orders"].groupby("klant_id").size().rename("n_orders")
    .reset_index()
    .merge(sheets["klanten"][["id", "naam"]], left_on="klant_id", right_on="id")
    .sort_values("n_orders", ascending=False)
    .head(5)
)
for _, r in top.iterrows():
    print(f"    {r['naam']!r}: {int(r['n_orders'])} orders")
PY

echo
echo ">>> Done. Output files:"
echo "  - ${DB_OUT}"
echo "  - ${XLSX_OUT}"

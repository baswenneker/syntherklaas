#!/usr/bin/env bash
# End-to-end smoke test: generate sample → run pipeline → verify with JOIN query.
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

DB_XLSX="/tmp/syntherklaas-demo-xlsx.db"
DB_CSV="/tmp/syntherklaas-demo-csv.db"
rm -f "${DB_XLSX}" "${DB_CSV}"

echo ">>> Pipeline 1/2: Excel input -> ${DB_XLSX} (cap 50 klanten)"
uv run python syntherklaas.py \
    --input "${PROJECT_ROOT}/example_data/xlsx/example_data.xlsx" \
    --db "${DB_XLSX}" \
    --max-rows 50

echo
echo ">>> Pipeline 2/2: CSV input -> ${DB_CSV} (cap 50 klanten)"
uv run python syntherklaas.py \
    --input "${PROJECT_ROOT}/example_data/csv" \
    --db "${DB_CSV}" \
    --max-rows 50

echo
echo ">>> Sanity check on ${DB_XLSX}:"
uv run python - <<PY
import sqlite3
conn = sqlite3.connect("${DB_XLSX}")
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
echo ">>> Done. Output DBs:"
echo "  - ${DB_XLSX}"
echo "  - ${DB_CSV}"

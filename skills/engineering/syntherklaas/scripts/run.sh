#!/usr/bin/env bash
set -euo pipefail

# Resolve scripts dir. When invoked by Claude Code, CLAUDE_SKILL_DIR points at
# the skill folder; fall back to the script's own location for direct CLI use.
if [[ -n "${CLAUDE_SKILL_DIR:-}" ]]; then
    SCRIPTS_DIR="${CLAUDE_SKILL_DIR}/scripts"
else
    SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

cd "${SCRIPTS_DIR}"

if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: uv not found. Install with:" >&2
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 4
fi

# First-run install: marker file in .venv signals deps + spacy model are ready.
INSTALL_MARKER=".venv/.syntherklaas-installed"
if [[ ! -f "${INSTALL_MARKER}" ]]; then
    echo ">>> First run: syncing dependencies via uv..."
    uv sync
    echo ">>> Downloading Spacy NL model (nl_core_news_md, ~43MB)..."
    uv run python -m spacy download nl_core_news_md
    mkdir -p "$(dirname "${INSTALL_MARKER}")"
    touch "${INSTALL_MARKER}"
    echo ">>> First-run install complete."
    echo
fi

exec uv run python "${SCRIPTS_DIR}/syntherklaas.py" "$@"

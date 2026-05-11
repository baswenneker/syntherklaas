#!/usr/bin/env bash
# smart-lint-wrapper.sh - Wrapper for smart-lint.sh that filters for modified and untracked files
#
# This script is designed to be called by the Stop hook.
# It detects modified files via git and runs smart-lint.sh only on relevant code files.
# Content-hash caching prevents redundant runs when nothing changed.
#
# Disable auto-lint by setting "smart-lint": false in .claude/fwd/plugin.json

# Read JSON input from stdin (Claude Code provides context via stdin for Stop hooks)
INPUT=$(cat)

# Loop protection: if stop_hook_active is true, a previous Stop hook already
# blocked Claude and the lint-fixer has run. Exit cleanly to avoid infinite loops.
STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)
if [ "$STOP_HOOK_ACTIVE" = "true" ]; then
    exit 0
fi

# Exit gracefully if not in a git repo
if [ ! -d .git ]; then
    exit 0
fi

# Check if smart-lint is disabled in plugin.json
PLUGIN_JSON="${CLAUDE_PROJECT_DIR:-.}/.claude/fwd/plugin.json"
if [ -f "$PLUGIN_JSON" ]; then
    SMART_LINT_ENABLED=$(jq -r 'if .["smart-lint"] == false then "false" else "true" end' "$PLUGIN_JSON" 2>/dev/null)
    if [ "$SMART_LINT_ENABLED" = "false" ]; then
        exit 0
    fi
fi

# Portable hashing command (macOS vs Linux) -- needed for content caching
if command -v md5 &>/dev/null; then
    hash_cmd() { md5 -q; }
elif command -v md5sum &>/dev/null; then
    hash_cmd() { md5sum | cut -d' ' -f1; }
else
    hash_cmd() { cat; }  # fallback: no hashing, always runs
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Get modified and untracked files (staged + unstaged changes + new files)
MODIFIED_FILES=$(git diff --name-only HEAD 2>/dev/null; git diff --cached --name-only 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null)

if [ -z "$MODIFIED_FILES" ]; then
    exit 0
fi

# Filter for relevant code file extensions
RELEVANT_FILES=$(echo "$MODIFIED_FILES" | grep -E '\.(ts|tsx|py|js|jsx|nix|ipynb|sh)$' | sort -u)

if [ -z "$RELEVANT_FILES" ]; then
    exit 0
fi

# --- Content hash caching: skip lint if nothing changed since last successful run ---

PROJECT_HASH=$(echo "$PWD" | hash_cmd)

# Build content fingerprint from:
# 1. The sorted list of relevant files
# 2. git diff HEAD for those files (unstaged + staged changes)
# 3. git diff --cached for those files (staged-only changes)
# 4. Contents of untracked relevant files
UNTRACKED_RELEVANT=$(comm -12 \
    <(git ls-files --others --exclude-standard 2>/dev/null | grep -E '\.(ts|tsx|py|js|jsx|nix|ipynb|sh)$' | sort) \
    <(echo "$RELEVANT_FILES"))

CONTENT_HASH=$(
    {
        echo "$RELEVANT_FILES"
        # shellcheck disable=SC2086
        git diff HEAD -- $RELEVANT_FILES 2>/dev/null
        # shellcheck disable=SC2086
        git diff --cached -- $RELEVANT_FILES 2>/dev/null
        if [ -n "$UNTRACKED_RELEVANT" ]; then
            echo "$UNTRACKED_RELEVANT" | while IFS= read -r f; do
                [ -f "$f" ] && cat "$f"
            done
        fi
    } | hash_cmd
)

# Cache location: /tmp/claude/lint-cache/lint-hash-<project-key>
CACHE_DIR="/tmp/claude/lint-cache"
CACHE_FILE="$CACHE_DIR/lint-hash-$PROJECT_HASH"

if [ -f "$CACHE_FILE" ] && [ "$(cat "$CACHE_FILE")" = "$CONTENT_HASH" ]; then
    exit 0
fi

# --- End caching check ---

# Display which files will be checked
echo ""
echo "Running lint checks on modified and untracked files:"
echo "$RELEVANT_FILES" | sed 's/^/  - /'
echo ""

# Run smart-lint.sh with specific files
# shellcheck disable=SC2086
"$SCRIPT_DIR/smart-lint.sh" --files $RELEVANT_FILES
EXIT_CODE=$?

# Cache the hash only after a successful lint run (exit 0).
# Exit 1 (missing deps) and exit 2 (lint issues) should NOT be cached,
# so lint re-runs next time to re-check.
if [ "$EXIT_CODE" -eq 0 ]; then
    mkdir -p "$CACHE_DIR"
    echo "$CONTENT_HASH" > "$CACHE_FILE"
fi

exit $EXIT_CODE

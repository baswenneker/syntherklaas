#!/usr/bin/env bash
# smart-lint.sh - Intelligent project-aware code quality checks for Claude Code
#
# SYNOPSIS
#   smart-lint.sh [options] [--files FILE1 FILE2 ...]
#
# DESCRIPTION
#   Automatically detects project type and runs ALL quality checks.
#   Every issue found is blocking - code must be 100% clean to proceed.
#
# OPTIONS
#   --debug       Enable debug output
#   --fast        Skip slow checks (import cycles, security scans)
#   --files       Check only specific files instead of entire project
#
# EXIT CODES
#   0 - Success (all checks passed - everything is GREEN)
#   1 - General error (missing dependencies, etc.)
#   2 - ANY issues found - ALL must be fixed
#
# CONFIGURATION
#   Project-specific overrides can be placed in .claude-hooks-config.sh
#   See inline documentation for all available options.

# Don't use set -e - we need to control exit codes carefully
set +e

# ============================================================================
# COLOR DEFINITIONS AND UTILITIES
# ============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Debug mode
CLAUDE_HOOKS_DEBUG="${CLAUDE_HOOKS_DEBUG:-0}"

# Logging functions
log_debug() {
    [[ "$CLAUDE_HOOKS_DEBUG" == "1" ]] && echo -e "${CYAN}[DEBUG]${NC} $*" >&2
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*" >&2
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $*" >&2
}

# Run a command, capture output, show on stderr if it fails
run_and_show_errors() {
    local output
    output=$("$@" 2>&1)
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        echo "$output" >&2
    fi
    return $exit_code
}

# Performance timing
time_start() {
    if [[ "$CLAUDE_HOOKS_DEBUG" == "1" ]]; then
        echo $(($(date +%s%N)/1000000))
    fi
}

time_end() {
    if [[ "$CLAUDE_HOOKS_DEBUG" == "1" ]]; then
        local start=$1
        local end=$(($(date +%s%N)/1000000))
        local duration=$((end - start))
        log_debug "Execution time: ${duration}ms"
    fi
}

# Check if a command exists
command_exists() {
    command -v "$1" &> /dev/null
}

# ============================================================================
# PROJECT DETECTION
# ============================================================================

detect_project_type() {
    local project_type="unknown"
    local types=()

    # Python project
    if [[ -f "pyproject.toml" ]] || [[ -f "setup.py" ]] || [[ -f "requirements.txt" ]] || [[ -n "$(find . -maxdepth 3 -name "*.py" -type f -print -quit 2>/dev/null)" ]]; then
        types+=("python")
    fi

    # JavaScript/TypeScript project
    if [[ -f "package.json" ]] || [[ -f "tsconfig.json" ]] || [[ -n "$(find . -maxdepth 3 \( -name "*.js" -o -name "*.ts" -o -name "*.jsx" -o -name "*.tsx" \) -type f -print -quit 2>/dev/null)" ]]; then
        types+=("javascript")
    fi

    # Nix project
    if [[ -f "flake.nix" ]] || [[ -f "default.nix" ]] || [[ -f "shell.nix" ]]; then
        types+=("nix")
    fi

    # Jupyter Notebook project
    if [[ -n "$(find . -maxdepth 3 -name "*.ipynb" -type f -print -quit 2>/dev/null)" ]]; then
        types+=("notebook")
    fi

    # Shell script project
    if [[ -n "$(find . -maxdepth 3 -name "*.sh" -type f -print -quit 2>/dev/null)" ]]; then
        types+=("shell")
    fi

    # Return primary type or "mixed" if multiple
    if [[ ${#types[@]} -eq 1 ]]; then
        project_type="${types[0]}"
    elif [[ ${#types[@]} -gt 1 ]]; then
        project_type="mixed:$(IFS=,; echo "${types[*]}")"
    fi

    log_debug "Detected project type: $project_type"
    echo "$project_type"
}

# Get list of modified files (if available from git)
get_modified_files() {
    if [[ -d .git ]] && command_exists git; then
        # Get files modified in the last commit or currently staged/modified
        git diff --name-only HEAD 2>/dev/null || true
        git diff --cached --name-only 2>/dev/null || true
    fi
}

# Check if we should skip a file
should_skip_file() {
    local file="$1"

    # Check .claude-hooks-ignore if it exists
    if [[ -f ".claude-hooks-ignore" ]]; then
        while IFS= read -r pattern; do
            # Skip comments and empty lines
            [[ -z "$pattern" || "$pattern" =~ ^[[:space:]]*# ]] && continue

            # Check if file matches pattern
            if [[ "$file" == $pattern ]]; then
                log_debug "Skipping $file due to .claude-hooks-ignore pattern: $pattern"
                return 0
            fi
        done < ".claude-hooks-ignore"
    fi

    # Check for inline skip comments
    if [[ -f "$file" ]] && head -n 5 "$file" 2>/dev/null | grep -q "claude-hooks-disable"; then
        log_debug "Skipping $file due to inline claude-hooks-disable comment"
        return 0
    fi

    return 1
}

# ============================================================================
# SUMMARY TRACKING
# ============================================================================

declare -a CLAUDE_HOOKS_SUMMARY=()
declare -i CLAUDE_HOOKS_ERROR_COUNT=0

add_summary() {
    local level="$1"
    local message="$2"

    if [[ "$level" == "error" ]]; then
        CLAUDE_HOOKS_ERROR_COUNT+=1
        CLAUDE_HOOKS_SUMMARY+=("${RED}x${NC} $message")
    else
        CLAUDE_HOOKS_SUMMARY+=("${GREEN}ok${NC} $message")
    fi
}

print_summary() {
    if [[ $CLAUDE_HOOKS_ERROR_COUNT -gt 0 ]]; then
        # Only show failures when there are errors
        echo -e "\n${BLUE}=== Summary ===${NC}" >&2
        for item in "${CLAUDE_HOOKS_SUMMARY[@]}"; do
            # Only print error items
            if [[ "$item" == *"x${NC}"* ]]; then
                echo -e "$item" >&2
            fi
        done

        echo -e "\n${RED}Found $CLAUDE_HOOKS_ERROR_COUNT issue(s) that MUST be fixed!${NC}" >&2
        echo -e "${RED}============================================${NC}" >&2
        echo -e "${RED}ALL ISSUES ARE BLOCKING${NC}" >&2
        echo -e "${RED}============================================${NC}" >&2
        echo -e "${RED}Fix EVERYTHING above until all checks are GREEN${NC}" >&2
    fi
    # Don't print success summary - we'll handle that in the final message
}

# ============================================================================
# CONFIGURATION LOADING
# ============================================================================

load_config() {
    # Default configuration
    export CLAUDE_HOOKS_ENABLED="${CLAUDE_HOOKS_ENABLED:-true}"
    export CLAUDE_HOOKS_FAIL_FAST="${CLAUDE_HOOKS_FAIL_FAST:-false}"
    export CLAUDE_HOOKS_SHOW_TIMING="${CLAUDE_HOOKS_SHOW_TIMING:-false}"

    # Language enables
    export CLAUDE_HOOKS_PYTHON_ENABLED="${CLAUDE_HOOKS_PYTHON_ENABLED:-true}"
    export CLAUDE_HOOKS_PYTHON_TYPECHECK_ENABLED="${CLAUDE_HOOKS_PYTHON_TYPECHECK_ENABLED:-true}"
    export CLAUDE_HOOKS_PYTHON_DOCCHECK_ENABLED="${CLAUDE_HOOKS_PYTHON_DOCCHECK_ENABLED:-false}"
    export CLAUDE_HOOKS_JS_ENABLED="${CLAUDE_HOOKS_JS_ENABLED:-true}"
    export CLAUDE_HOOKS_NIX_ENABLED="${CLAUDE_HOOKS_NIX_ENABLED:-false}"
    export CLAUDE_HOOKS_NOTEBOOK_ENABLED="${CLAUDE_HOOKS_NOTEBOOK_ENABLED:-true}"
    export CLAUDE_HOOKS_NOTEBOOK_TYPECHECK_ENABLED="${CLAUDE_HOOKS_NOTEBOOK_TYPECHECK_ENABLED:-false}"
    export CLAUDE_HOOKS_SHELL_ENABLED="${CLAUDE_HOOKS_SHELL_ENABLED:-true}"

    # Project-specific overrides
    if [[ -f ".claude-hooks-config.sh" ]]; then
        source ".claude-hooks-config.sh" || {
            log_error "Failed to load .claude-hooks-config.sh"
            exit 2
        }
    fi

    # Quick exit if hooks are disabled
    if [[ "$CLAUDE_HOOKS_ENABLED" != "true" ]]; then
        log_info "Claude hooks are disabled"
        exit 0
    fi
}

# ============================================================================
# COMMON HELPERS
# ============================================================================

# run_makefile_or_tool <target> <success_msg> <error_msg> <fallback_fn>
# Checks if Makefile has the target, runs it if so, otherwise calls fallback.
run_makefile_or_tool() {
    local target="$1"
    local success_msg="$2"
    local error_msg="$3"
    local fallback_fn="$4"

    if [[ -f "Makefile" ]] && grep -qE "^${target}:" Makefile 2>/dev/null; then
        log_info "Using Makefile target: $target"
        if ! run_and_show_errors make "$target"; then
            add_summary "error" "$error_msg"
        else
            add_summary "success" "$success_msg"
        fi
    else
        "$fallback_fn"
    fi
}

# run_formatter <check_cmd_array> <fix_cmd_array> <success_msg> <fixed_msg>
# Runs formatter in check mode; if dirty, auto-fixes and reports success with note.
# Usage: run_formatter "success msg" "auto-fixed msg" check_cmd... -- fix_cmd...
run_formatter() {
    local success_msg="$1"
    local fixed_msg="$2"
    shift 2

    # Split args at "--" into check_cmd and fix_cmd
    local -a check_cmd=()
    local -a fix_cmd=()
    local past_separator=false
    for arg in "$@"; do
        if [[ "$arg" == "--" ]]; then
            past_separator=true
            continue
        fi
        if $past_separator; then
            fix_cmd+=("$arg")
        else
            check_cmd+=("$arg")
        fi
    done

    if "${check_cmd[@]}" 2>/dev/null; then
        add_summary "success" "$success_msg"
    else
        "${fix_cmd[@]}" 2>/dev/null
        add_summary "success" "$fixed_msg (auto-formatted)"
    fi
}

# filter_skippable_files <file_list_string>
# Applies should_skip_file() to filter file lists. Returns filtered list.
filter_skippable_files() {
    local files="$1"
    local filtered=""
    for f in $files; do
        if ! should_skip_file "$f"; then
            filtered="$filtered $f"
        fi
    done
    echo "${filtered# }"
}

# ============================================================================
# LANGUAGE LINTERS
# ============================================================================

# --- Python helpers (called as fallbacks by run_makefile_or_tool) ---

_python_fmt_fallback() {
    local python_files="${_CURRENT_PYTHON_FILES}"
    if command_exists black; then
        local black_target="${python_files:-.}"
        # shellcheck disable=SC2086
        run_formatter "Python formatting correct" "Python files formatted" \
            black $black_target --check --quiet -- \
            black $black_target --quiet
    else
        log_info "black not found - install with: pip install black"
    fi
}

_python_lint_fallback() {
    local python_files="${_CURRENT_PYTHON_FILES}"
    if command_exists ruff; then
        local ruff_target="${python_files:-.}"
        # shellcheck disable=SC2086
        if ! run_and_show_errors ruff check --fix $ruff_target; then
            add_summary "error" "Ruff found issues"
        else
            add_summary "success" "Ruff check passed"
        fi
    elif command_exists flake8; then
        local flake8_target="${python_files:-.}"
        # shellcheck disable=SC2086
        if run_and_show_errors flake8 $flake8_target; then
            add_summary "success" "Flake8 check passed"
        else
            add_summary "error" "Flake8 found issues"
        fi
    else
        log_info "ruff or flake8 not found - install with: pip install ruff"
    fi
}

_python_typecheck_fallback() {
    local python_files="${_CURRENT_PYTHON_FILES}"
    if command_exists pyright; then
        local pyright_target="${python_files:-.}"
        # shellcheck disable=SC2086
        if ! run_and_show_errors pyright $pyright_target; then
            add_summary "error" "Type errors found (pyright)"
        else
            add_summary "success" "Type checking passed (pyright)"
        fi
    elif command_exists mypy; then
        local mypy_target="${python_files:-.}"
        # shellcheck disable=SC2086
        if ! run_and_show_errors mypy $mypy_target; then
            add_summary "error" "Type errors found (mypy)"
        else
            add_summary "success" "Type checking passed (mypy)"
        fi
    else
        log_info "pyright or mypy not found - install with: pip install pyright"
    fi
}

_python_doc_check() {
    if [[ "${CLAUDE_HOOKS_PYTHON_DOCCHECK_ENABLED:-false}" != "true" ]]; then
        return 0
    fi

    local python_files="${_CURRENT_PYTHON_FILES}"
    log_info "Running Python docstring checks..."

    if command_exists ruff; then
        local ruff_target="${python_files:-.}"
        # shellcheck disable=SC2086
        if run_and_show_errors ruff check --select D $ruff_target; then
            add_summary "success" "Python docstring check passed (ruff/pydocstyle)"
        else
            add_summary "error" "Python docstring issues found (ruff/pydocstyle)"
        fi
    elif command_exists interrogate; then
        local interrogate_target="${python_files:-.}"
        # shellcheck disable=SC2086
        if run_and_show_errors interrogate $interrogate_target; then
            add_summary "success" "Python docstring check passed (interrogate)"
        else
            add_summary "error" "Python docstring coverage too low (interrogate)"
        fi
    else
        log_info "Docstring checking requires ruff or interrogate - skipping"
    fi
}

lint_python() {
    if [[ "${CLAUDE_HOOKS_PYTHON_ENABLED:-true}" != "true" ]]; then
        log_debug "Python linting disabled"
        return 0
    fi

    log_info "Running Python linters..."

    # Filter for Python files if TARGET_FILES specified
    local python_files=""
    if [[ -n "$CLAUDE_HOOKS_TARGET_FILES" ]]; then
        python_files=$(echo "$CLAUDE_HOOKS_TARGET_FILES" | tr ' ' '\n' | grep -E '\.py$' | tr '\n' ' ')
        python_files=$(filter_skippable_files "$python_files")
        if [[ -z "$python_files" ]]; then
            log_debug "No Python files in target files, skipping Python checks"
            return 0
        fi
        log_debug "Checking Python files: $python_files"
    fi

    # Store for use by fallback functions
    _CURRENT_PYTHON_FILES="$python_files"

    # Formatting
    run_makefile_or_tool "fmt" "Python code formatted" "Python formatting failed (make fmt)" _python_fmt_fallback

    # Linting
    run_makefile_or_tool "lint" "Python linting passed" "Python linting failed (make lint)" _python_lint_fallback

    # Type checking
    if [[ "${CLAUDE_HOOKS_PYTHON_TYPECHECK_ENABLED:-true}" == "true" ]]; then
        log_info "Running Python type checking..."
        run_makefile_or_tool "typecheck" "Type checking passed" "Type checking failed (make typecheck)" _python_typecheck_fallback
    fi

    # Docstring checking (opt-in)
    _python_doc_check

    return 0
}

lint_javascript() {
    if [[ "${CLAUDE_HOOKS_JS_ENABLED:-true}" != "true" ]]; then
        log_debug "JavaScript linting disabled"
        return 0
    fi

    log_info "Running JavaScript/TypeScript linters..."

    # Filter for JS/TS files if TARGET_FILES specified
    local js_files=""
    if [[ -n "$CLAUDE_HOOKS_TARGET_FILES" ]]; then
        js_files=$(echo "$CLAUDE_HOOKS_TARGET_FILES" | tr ' ' '\n' | grep -E '\.(js|jsx|ts|tsx)$' | tr '\n' ' ')
        js_files=$(filter_skippable_files "$js_files")
        if [[ -z "$js_files" ]]; then
            log_debug "No JavaScript/TypeScript files in target files, skipping JS checks"
            return 0
        fi
        log_debug "Checking JS/TS files: $js_files"
    fi

    # Check for ESLint
    if [[ -f "package.json" ]] && grep -q "eslint" package.json 2>/dev/null; then
        if command_exists npm; then
            if [[ -n "$js_files" ]]; then
                # shellcheck disable=SC2086
                if run_and_show_errors npx eslint $js_files; then
                    add_summary "success" "ESLint check passed"
                else
                    add_summary "error" "ESLint found issues"
                fi
            else
                if run_and_show_errors npm run lint --if-present; then
                    add_summary "success" "ESLint check passed"
                else
                    add_summary "error" "ESLint found issues"
                fi
            fi
        else
            log_info "npm not found - install Node.js and npm"
        fi

        # Log JSDoc status if eslint-plugin-jsdoc is configured
        if grep -q "eslint-plugin-jsdoc" package.json 2>/dev/null; then
            log_info "JSDoc rules active via eslint-plugin-jsdoc"
        fi
    else
        log_debug "No ESLint configuration found, skipping ESLint"
    fi

    # Prettier
    if [[ -f ".prettierrc" ]] || [[ -f "prettier.config.js" ]] || [[ -f ".prettierrc.json" ]]; then
        local prettier_target="${js_files:-.}"
        if command_exists prettier; then
            # shellcheck disable=SC2086
            run_formatter "Prettier formatting correct" "Prettier formatting fixed" \
                prettier --check $prettier_target -- \
                prettier --write $prettier_target
        elif command_exists npx; then
            # shellcheck disable=SC2086
            run_formatter "Prettier formatting correct" "Prettier formatting fixed" \
                npx prettier --check $prettier_target -- \
                npx prettier --write $prettier_target
        else
            log_info "prettier not found - install with: npm install -g prettier"
        fi
    else
        log_debug "No Prettier configuration found, skipping Prettier"
    fi

    return 0
}

lint_nix() {
    if [[ "${CLAUDE_HOOKS_NIX_ENABLED:-true}" != "true" ]]; then
        log_debug "Nix linting disabled"
        return 0
    fi

    log_info "Running Nix linters..."

    # Filter for Nix files if TARGET_FILES specified
    local nix_files=""
    if [[ -n "$CLAUDE_HOOKS_TARGET_FILES" ]]; then
        nix_files=$(echo "$CLAUDE_HOOKS_TARGET_FILES" | tr ' ' '\n' | grep -E '\.nix$' | tr '\n' ' ')
        nix_files=$(filter_skippable_files "$nix_files")
        if [[ -z "$nix_files" ]]; then
            log_debug "No Nix files in target files, skipping Nix checks"
            return 0
        fi
        log_debug "Checking Nix files: $nix_files"
    else
        # Find all .nix files
        nix_files=$(find . -name "*.nix" -type f | grep -v -E "(result/|/nix/store/)" | head -20 | tr '\n' ' ')
    fi

    if [[ -z "$nix_files" ]]; then
        log_debug "No Nix files found"
        return 0
    fi

    # Check formatting with nixpkgs-fmt or alejandra
    if command_exists nixpkgs-fmt; then
        # shellcheck disable=SC2086
        run_formatter "Nix formatting correct" "Nix files formatted" \
            nixpkgs-fmt --check $nix_files -- \
            nixpkgs-fmt $nix_files
    elif command_exists alejandra; then
        # shellcheck disable=SC2086
        run_formatter "Nix formatting correct" "Nix files formatted" \
            alejandra --check $nix_files -- \
            alejandra --quiet $nix_files
    else
        log_info "nixpkgs-fmt or alejandra not found - install with: nix-env -iA nixpkgs.nixpkgs-fmt"
    fi

    # Static analysis with statix
    if command_exists statix; then
        if run_and_show_errors statix check; then
            add_summary "success" "Statix check passed"
        else
            add_summary "error" "Statix found issues"
        fi
    else
        log_info "statix not found - install with: nix-env -iA nixpkgs.statix"
    fi

    return 0
}

lint_notebook() {
    if [[ "${CLAUDE_HOOKS_NOTEBOOK_ENABLED:-true}" != "true" ]]; then
        log_debug "Notebook linting disabled"
        return 0
    fi

    log_info "Running Jupyter Notebook linters..."

    # Filter for notebook files if TARGET_FILES specified
    local notebook_files=""
    if [[ -n "$CLAUDE_HOOKS_TARGET_FILES" ]]; then
        notebook_files=$(echo "$CLAUDE_HOOKS_TARGET_FILES" | tr ' ' '\n' | grep -E '\.ipynb$' | tr '\n' ' ')
        notebook_files=$(filter_skippable_files "$notebook_files")
        if [[ -z "$notebook_files" ]]; then
            log_debug "No Jupyter notebook files in target files, skipping notebook checks"
            return 0
        fi
        log_debug "Checking notebook files: $notebook_files"
    else
        # Find all .ipynb files (exclude checkpoints)
        notebook_files=$(find . -name "*.ipynb" -type f | grep -v ".ipynb_checkpoints" | head -20 | tr '\n' ' ')
    fi

    if [[ -z "$notebook_files" ]]; then
        log_debug "No Jupyter notebook files found"
        return 0
    fi

    # Check if nbqa is available
    if ! command_exists nbqa; then
        log_info "nbqa not found - install with: pip install nbqa"
        log_info "   nbqa allows running Python linters (black, ruff, pyright) on Jupyter notebooks"
        return 0
    fi

    # Black formatting via nbqa
    if command_exists black; then
        log_debug "Running nbqa black on notebooks..."
        # shellcheck disable=SC2086
        run_formatter "Notebook formatting correct (black)" "Notebook files formatted (black)" \
            nbqa black $notebook_files --check --quiet -- \
            nbqa black $notebook_files --quiet
    else
        log_debug "black not found, skipping notebook formatting"
    fi

    # Ruff linting via nbqa
    if command_exists ruff; then
        log_debug "Running nbqa ruff on notebooks..."
        # shellcheck disable=SC2086
        if run_and_show_errors nbqa ruff check --fix $notebook_files; then
            add_summary "success" "Notebook lint check passed (ruff)"
        else
            add_summary "error" "Notebook lint issues found (ruff)"
        fi
    elif command_exists flake8; then
        log_debug "Running nbqa flake8 on notebooks..."
        # shellcheck disable=SC2086
        if run_and_show_errors nbqa flake8 $notebook_files; then
            add_summary "success" "Notebook lint check passed (flake8)"
        else
            add_summary "error" "Notebook lint issues found (flake8)"
        fi
    else
        log_debug "ruff/flake8 not found, skipping notebook linting"
    fi

    # Type checking via nbqa (disabled by default for notebooks)
    if [[ "${CLAUDE_HOOKS_NOTEBOOK_TYPECHECK_ENABLED:-false}" == "true" ]]; then
        if command_exists pyright; then
            log_debug "Running nbqa pyright on notebooks..."
            # shellcheck disable=SC2086
            if run_and_show_errors nbqa pyright $notebook_files; then
                add_summary "success" "Notebook type check passed (pyright)"
            else
                add_summary "error" "Notebook type errors found (pyright)"
            fi
        elif command_exists mypy; then
            log_debug "Running nbqa mypy on notebooks..."
            # shellcheck disable=SC2086
            if run_and_show_errors nbqa mypy $notebook_files; then
                add_summary "success" "Notebook type check passed (mypy)"
            else
                add_summary "error" "Notebook type errors found (mypy)"
            fi
        else
            log_debug "pyright/mypy not found, skipping notebook type checking"
        fi
    fi

    return 0
}

lint_shell() {
    if [[ "${CLAUDE_HOOKS_SHELL_ENABLED:-true}" != "true" ]]; then
        log_debug "Shell linting disabled"
        return 0
    fi

    log_info "Running shell script linters..."

    # Filter for shell files if TARGET_FILES specified
    local shell_files=""
    if [[ -n "$CLAUDE_HOOKS_TARGET_FILES" ]]; then
        shell_files=$(echo "$CLAUDE_HOOKS_TARGET_FILES" | tr ' ' '\n' | grep -E '\.sh$' | tr '\n' ' ')
        shell_files=$(filter_skippable_files "$shell_files")
        if [[ -z "$shell_files" ]]; then
            log_debug "No shell files in target files, skipping shell checks"
            return 0
        fi
        log_debug "Checking shell files: $shell_files"
    else
        # Find all .sh files (exclude node_modules, .git, vendor)
        shell_files=$(find . -name "*.sh" -type f | grep -v -E "(node_modules/|\.git/|vendor/)" | head -50 | tr '\n' ' ')
    fi

    if [[ -z "$shell_files" ]]; then
        log_debug "No shell files found"
        return 0
    fi

    if command_exists shellcheck; then
        # shellcheck disable=SC2086
        if run_and_show_errors shellcheck --severity=warning $shell_files; then
            add_summary "success" "ShellCheck passed"
        else
            add_summary "error" "ShellCheck found issues"
        fi
    else
        log_info "shellcheck not found - install with: brew install shellcheck (or apt install shellcheck)"
    fi

    return 0
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

# Parse command line options
FAST_MODE=false
TARGET_FILES=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --debug)
            export CLAUDE_HOOKS_DEBUG=1
            shift
            ;;
        --fast)
            FAST_MODE=true
            shift
            ;;
        --files)
            shift
            # Collect all remaining arguments as files
            while [[ $# -gt 0 ]] && [[ "$1" != --* ]]; do
                TARGET_FILES+=("$1")
                shift
            done
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
    esac
done

# Export target files for use in lint functions
export CLAUDE_HOOKS_TARGET_FILES="${TARGET_FILES[*]}"
log_debug "Target files: ${CLAUDE_HOOKS_TARGET_FILES:-all files}"

# Print header
echo "" >&2
echo "Style Check - Validating code formatting..." >&2
echo "--------------------------------------------" >&2

# Load configuration
load_config

# Start timing
START_TIME=$(time_start)

# Detect project type
PROJECT_TYPE=$(detect_project_type)
log_info "Project type: $PROJECT_TYPE"

# Dispatch to the correct linter for a given type
run_linter_for_type() {
    case "$1" in
        "python") lint_python ;;
        "javascript") lint_javascript ;;
        "nix") lint_nix ;;
        "notebook") lint_notebook ;;
        "shell") lint_shell ;;
    esac
}

# Main execution
main() {
    # Handle mixed project types
    if [[ "$PROJECT_TYPE" == mixed:* ]]; then
        local types="${PROJECT_TYPE#mixed:}"
        IFS=',' read -ra TYPE_ARRAY <<< "$types"

        for type in "${TYPE_ARRAY[@]}"; do
            run_linter_for_type "$type"

            # Fail fast if configured
            if [[ "$CLAUDE_HOOKS_FAIL_FAST" == "true" && $CLAUDE_HOOKS_ERROR_COUNT -gt 0 ]]; then
                break
            fi
        done
    else
        # Single project type
        case "$PROJECT_TYPE" in
            "unknown")
                log_info "No recognized project type, skipping checks"
                ;;
            *)
                run_linter_for_type "$PROJECT_TYPE"
                ;;
        esac
    fi

    # Show timing if enabled
    time_end "$START_TIME"

    # Print summary
    print_summary

    # Return exit code - any issues mean failure
    if [[ $CLAUDE_HOOKS_ERROR_COUNT -gt 0 ]]; then
        return 2
    else
        return 0
    fi
}

# Run main function
main
exit_code=$?

# Final message and exit
if [[ $exit_code -eq 2 ]]; then
    echo -e "\n${RED}FAILED - Fix all issues above!${NC}" >&2
    echo -e "${YELLOW}NEXT STEPS:${NC}" >&2
    echo -e "${YELLOW}  1. Fix the issues listed above${NC}" >&2
    echo -e "${YELLOW}  2. Verify the fix by running the lint command again${NC}" >&2
    echo -e "${YELLOW}  3. Continue with your original task${NC}" >&2
    exit 2
else
    echo -e "\n${GREEN}All checks passed!${NC}" >&2
    exit 0
fi

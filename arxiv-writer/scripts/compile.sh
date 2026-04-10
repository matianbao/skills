#!/bin/bash
# compile.sh — LaTeX compilation with error detection and structured output
# Usage: bash compile.sh [main_file_without_extension]
#
# Exit codes:
#   0 = success, no issues
#   1 = fatal error (compilation failed)
#   2 = compiled but has warnings (undefined refs, overfull boxes)

set -euo pipefail

export PATH="/Library/TeX/texbin:/usr/local/texlive/2024/bin/universal-darwin:/usr/local/texlive/2026basic/bin/universal-darwin:$PATH"

MAIN="${1:-main}"
LOG="${MAIN}.log"

# Colors (disabled if not a terminal)
if [ -t 1 ]; then
    RED='\033[0;31m'; YELLOW='\033[0;33m'; GREEN='\033[0;32m'; NC='\033[0m'
else
    RED=''; YELLOW=''; GREEN=''; NC=''
fi

echo "=== Compiling ${MAIN}.tex ==="

# --- Pass 1: pdflatex ---
if ! pdflatex -interaction=nonstopmode -halt-on-error "${MAIN}.tex" > /dev/null 2>&1; then
    echo -e "${RED}FATAL: pdflatex pass 1 failed${NC}"
    # Extract error lines from log
    if [ -f "$LOG" ]; then
        echo ""
        echo "=== ERRORS ==="
        grep -A 2 "^!" "$LOG" 2>/dev/null | head -30
        echo ""
        echo "=== Missing files ==="
        grep "File .* not found" "$LOG" 2>/dev/null | head -10
        grep "LaTeX Error:" "$LOG" 2>/dev/null | head -10
    fi
    exit 1
fi

# --- BibTeX ---
if [ -f "references.bib" ]; then
    bibtex "${MAIN}" > /dev/null 2>&1 || true
fi

# --- Pass 2 & 3: resolve references ---
pdflatex -interaction=nonstopmode "${MAIN}.tex" > /dev/null 2>&1 || true
pdflatex -interaction=nonstopmode "${MAIN}.tex" > /dev/null 2>&1 || true

# --- Analyze log ---
EXIT_CODE=0

if [ ! -f "$LOG" ]; then
    echo -e "${RED}FATAL: No log file produced${NC}"
    exit 1
fi

# Count issues: grep -c outputs "0" and exits 1 when no match; capture output, fallback only if grep itself errors
count() { local n; n=$(grep -c "$1" "$LOG" 2>/dev/null) && echo "$n" || echo "${n:-0}"; }
FATAL_ERRORS=$(count "^!")
UNDEF_CITE=$(count "Citation.*undefined")
UNDEF_REF=$(count "Reference.*undefined")
OVERFULL=$(count "Overfull")
UNDERFULL=$(count "Underfull")
MISSING_FIG=$(count "File.*not found")

# Report
echo ""
echo "=== Compilation Report ==="

if [ "$FATAL_ERRORS" -gt 0 ]; then
    echo -e "${RED}ERRORS: ${FATAL_ERRORS}${NC}"
    grep -A 2 "^!" "$LOG" 2>/dev/null | head -30
    EXIT_CODE=1
fi

if [ "$UNDEF_CITE" -gt 0 ]; then
    echo -e "${YELLOW}Undefined citations: ${UNDEF_CITE}${NC}"
    grep "Citation.*undefined" "$LOG" 2>/dev/null | sed 's/.*Citation `\(.*\)'"'"'.*/  \\cite{\1}/' | sort -u | head -20
    EXIT_CODE=2
fi

if [ "$UNDEF_REF" -gt 0 ]; then
    echo -e "${YELLOW}Undefined references: ${UNDEF_REF}${NC}"
    grep "Reference.*undefined" "$LOG" 2>/dev/null | sed 's/.*Reference `\(.*\)'"'"'.*/  \\ref{\1}/' | sort -u | head -20
    EXIT_CODE=2
fi

if [ "$MISSING_FIG" -gt 0 ]; then
    echo -e "${YELLOW}Missing files: ${MISSING_FIG}${NC}"
    grep "File.*not found" "$LOG" 2>/dev/null | head -10
    [ "$EXIT_CODE" -lt 2 ] && EXIT_CODE=2
fi

if [ "$OVERFULL" -gt 0 ] || [ "$UNDERFULL" -gt 0 ]; then
    echo -e "${YELLOW}Box warnings: ${OVERFULL} overfull, ${UNDERFULL} underfull${NC}"
    # Only show severe overfull (>10pt)
    SEVERE=$(grep "Overfull" "$LOG" 2>/dev/null | grep -cE "[1-9][0-9]+\.[0-9]+pt" 2>/dev/null; true)
    SEVERE=${SEVERE:-0}
    if [ "$SEVERE" -gt 0 ]; then
        echo -e "  ${YELLOW}Severe (>10pt): ${SEVERE}${NC}"
        grep "Overfull" "$LOG" 2>/dev/null | grep -E "[1-9][0-9]+\.[0-9]+pt" | head -5
        [ "$EXIT_CODE" -lt 2 ] && EXIT_CODE=2
    fi
fi

if [ "$EXIT_CODE" -eq 0 ]; then
    echo -e "${GREEN}OK: No issues detected${NC}"
fi

echo ""
echo "=== Done ==="
echo "Output: ${MAIN}.pdf"
echo "Status: $([ $EXIT_CODE -eq 0 ] && echo 'CLEAN' || ([ $EXIT_CODE -eq 1 ] && echo 'FAILED' || echo 'WARNINGS'))"

exit $EXIT_CODE

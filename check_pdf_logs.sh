#!/bin/bash
# Script to check PDF generation logs

LOG_FILE="backend/data/logs/pdf_generation.log"

echo "=== PDF Generation Logs ==="
echo ""

if [ ! -f "$LOG_FILE" ]; then
    echo "Log file not found: $LOG_FILE"
    echo "Generate a PDF first to create the log file."
    exit 1
fi

echo "--- Recent PDF generation logs (last 50 lines) ---"
echo ""
tail -50 "$LOG_FILE"

echo ""
echo "--- Summary: Word Count Analysis ---"
echo ""
grep "Result:" "$LOG_FILE" | tail -10 | while IFS= read -r line; do
    echo "$line"
done

echo ""
echo "To see logs in real-time, run:"
echo "  tail -f $LOG_FILE"

#!/bin/sh
export PYTHONPATH=/app/share/ai-file-cleaner:$PYTHONPATH
exec python3 -m ai_cleaner "$@"

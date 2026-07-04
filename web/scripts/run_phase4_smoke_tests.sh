#!/usr/bin/env bash
set -euo pipefail

cd /app
python -m unittest discover -s tests -p 'test_*.py'
python -m compileall -q /app/app

echo "OK: smoke tests Fase 4 ejecutados correctamente."

#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
[ -f ".venv/bin/python" ] && PYTHON=".venv/bin/python" || PYTHON="python3"
"$PYTHON" WeLearn_Helper.py

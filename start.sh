# !/user/bin/env bash


set -e # 途中でエラーが出たら即終了

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "$SCRIPT_DIR"

PROJECT_DIR="$SCRIPT_DIR/inventry_checker"
cd "$PROJECT_DIR"

VENV_DIR="$PROJECT_DIR/.venv/bin/activate"
# VENV_DIR="/.venv/bin/activate"
# echo "env file: $VENV_DIR"

PYTHON_APP="$PROJECT_DIR/inventry_checker/"
# PYTHON_APP="/inventry_checker/manage.py"
# echo "python file: $PYTHON_APP"
cd "$PYTHON_APP"

source "$VENV_DIR"


# FIXED_ARGS="runserver"
python3 "manage.py" "runserver"


# command -v firefox >/dev/null 2?&1;
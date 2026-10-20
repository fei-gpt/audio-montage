#!/bin/sh
set -eu
task_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -n "${MONTAGE_PYTHON:-}" ]; then
    task_python=$MONTAGE_PYTHON
elif [ -x "$task_dir/.venv/bin/python" ]; then
    task_python="$task_dir/.venv/bin/python"
elif [ -x "$task_dir/../../work/montage-venv/bin/python" ]; then
    task_python="$task_dir/../../work/montage-venv/bin/python"
else
    task_python=python3
fi
exec "$task_python" "$task_dir/montage.py" "$@"

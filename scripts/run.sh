#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export UV_PYTHON_INSTALL_DIR="$PWD/.python"
export UV_CACHE_DIR="$PWD/.cache/uv"
export HF_HOME="$PWD/.cache/huggingface"
export TIKTOKEN_CACHE_DIR="$PWD/.cache/tiktoken"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
if command -v uv >/dev/null 2>&1; then
  runner=uv
else
  runner="$PWD/.tools/uv/bin/uv"
fi
case "${1:-check}" in
  check)
    "$runner" run --frozen python scripts/check_setup.py --send
    ;;
  preview)
    "$runner" run --frozen python scripts/check_setup.py
    "$runner" run --frozen src/zotero_arxiv_daily/main.py executor.debug=true executor.dry_run=true executor.max_paper_num=3
    ;;
  test-email)
    "$runner" run --frozen python scripts/check_setup.py --send
    "$runner" run --frozen src/zotero_arxiv_daily/main.py executor.debug=true executor.dry_run=false executor.max_paper_num=3
    ;;
  daily)
    "$runner" run --frozen python scripts/check_setup.py --send
    "$runner" run --frozen src/zotero_arxiv_daily/main.py executor.debug=false executor.dry_run=false
    ;;
  *)
    echo 'Usage: sh scripts/run.sh check|preview|test-email|daily' >&2
    exit 2
    ;;
esac

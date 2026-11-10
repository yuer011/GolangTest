#!/bin/bash
# 在独立 Terminal.app 窗口运行 Mac 数据安全回归 case。
set -euo pipefail

usage() {
  cat <<'EOF'
用法：
  scripts/run_regression_mac.sh [--filter TEXT] [--debug-shots] [--keep-browser-open]

示例：
  scripts/run_regression_mac.sh \
    --filter regression.screen_watermark.create_preview_save \
    --debug-shots \
    --keep-browser-open

脚本立即返回；回归 run 在独立 Terminal.app 窗口执行，本地产物写入
reports/regression/<run_id>/，不触发飞书多维表格或覆盖率同步。
EOF
}

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
FILTER=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --filter)
      [[ $# -ge 2 ]] || { echo "--filter 缺少参数" >&2; exit 2; }
      FILTER="$2"
      shift 2
      ;;
    --debug-shots)
      EXTRA_ARGS+=("$1")
      shift
      ;;
    --keep-browser-open)
      EXTRA_ARGS+=("$1")
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数：$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -x "$PYTHON" ]]; then
  echo "找不到虚拟环境 Python：$PYTHON" >&2
  exit 1
fi

RUN_TOKEN="$(date -u +%Y%m%dT%H%M%S)_$$_${RANDOM}"
RUN_DIR="$PROJECT_ROOT/.tmp/mac_regression_runs"
RUNNER="$RUN_DIR/run_regression_mac_${RUN_TOKEN}.sh"
OUT="$RUN_DIR/${RUN_TOKEN}.out"
DONE="$RUN_DIR/${RUN_TOKEN}.done"
META="$PROJECT_ROOT/.tmp/last_regression_run_mac.env"
mkdir -p "$RUN_DIR"

COMMAND=("$PYTHON" -m dlp_auto.regression.run)
if [[ -n "$FILTER" ]]; then
  COMMAND+=(--filter "$FILTER")
fi
COMMAND+=("${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}")

{
  printf '#!/bin/bash\n'
  printf 'set -o pipefail\n'
  printf 'PROJECT_ROOT=%q\n' "$PROJECT_ROOT"
  printf 'PYTHON=%q\n' "$PYTHON"
  printf 'OUT=%q\n' "$OUT"
  printf 'DONE=%q\n' "$DONE"
  printf 'TITLE_TOKEN=%q\n' "DLP-REGRESSION-MAC-$RUN_TOKEN"
  printf 'cd "$PROJECT_ROOT" || exit 1\n'
  printf 'COMMAND=('
  printf ' %q' "${COMMAND[@]}"
  printf ' )\n'
  cat <<'EOF'
printf '\033]0;%s\007' "$TITLE_TOKEN"
"${COMMAND[@]}" 2>&1 | tee "$OUT"
rc=${PIPESTATUS[0]}
echo "$rc" > "$DONE"
echo "RUN_EXIT=$rc"
nohup "$PYTHON" "$PROJECT_ROOT/scripts/close_terminal_window.py" \
  "$TITLE_TOKEN" --delay 1 </dev/null >/dev/null 2>&1 &
exit "$rc"
EOF
} > "$RUNNER"
chmod +x "$RUNNER"

{
  printf 'RUN_TOKEN=%q\n' "$RUN_TOKEN"
  printf 'RUNNER=%q\n' "$RUNNER"
  printf 'OUT=%q\n' "$OUT"
  printf 'DONE=%q\n' "$DONE"
} > "$META"

"$PYTHON" "$PROJECT_ROOT/scripts/open_terminal_runner.py" "$RUNNER"
echo "已在独立 Terminal.app 窗口启动 Mac 回归 run"
echo "输出：$OUT"
echo "退出码：$DONE"

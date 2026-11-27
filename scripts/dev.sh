#!/usr/bin/env bash
# ============================================================================
#  LangGraph Agent - 前后端一键启动（Windows / Git Bash / macOS / Linux）
#
#  用法：
#    bash scripts/dev.sh
#
#  后端 : http://127.0.0.1:2024      （LangGraph API）
#  前端 : http://localhost:5173/app/ （Vite 开发服务器）
#
#  按 Ctrl+C 一并停止前后端。Windows 原生 CMD 请改用 scripts\dev.bat
#  （CMD 下需处理 GBK 编码问题，详见 scripts\dev-backend.bat 的文件头说明）。
# ============================================================================
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"

if [ ! -d "$VENV" ]; then
  echo "[错误] 未找到虚拟环境: $VENV"
  echo "请先执行:"
  echo "  cd backend && python -m venv .venv"
  echo "  .venv/Scripts/python.exe -m pip install -i https://mirrors.aliyun.com/pypi/simple/ --no-build-isolation -e . \"langgraph-cli[inmem]\" colorama"
  exit 1
fi

# 迁移自检：editable 安装的 .pth 与 console script 的 shebang 都写死了绝对路径，
# 换目录拷贝后仍指向旧位置，旧目录一删就崩。这里提前发现并给出修复动作。
# 注意：比较双方都走 Python 归一化，避免 Git Bash 的 /d/... 与 D:\... 格式差异误报。
if ! (cd "$BACKEND" && "$VENV/Scripts/python.exe" -c "
import agent, os, sys, pathlib
resolved = pathlib.Path(agent.__file__).resolve()
expected = pathlib.Path(os.getcwd()).resolve()
if not str(resolved).lower().startswith(str(expected).lower()):
    print('MISMATCH:', resolved)
    sys.exit(1)
" 2>/dev/null); then
  echo "[错误] 虚拟环境仍指向旧路径（目录迁移后 .pth / shebang 未更新）。"
  echo "  修复方式（重建 venv，约 2 分钟）:"
  echo "    cd backend && rm -rf .venv"
  echo "    python -m venv .venv"
  echo "    .venv/Scripts/python.exe -m pip install -i https://mirrors.aliyun.com/pypi/simple/ --no-build-isolation -e . \"langgraph-cli[inmem]\" colorama"
  exit 1
fi

if [ ! -f "$BACKEND/.env" ]; then
  echo "[警告] 未找到 backend/.env，LLM API Key 未配置，Agent 调用会失败。"
  echo "  参见 backend/.env.example 或 README 的配置说明。"
fi

echo "[1/2] 启动后端 LangGraph (127.0.0.1:2024)..."
(cd "$BACKEND" && "$VENV/Scripts/langgraph.exe" dev --no-browser --port 2024) &
BACKEND_PID=$!

sleep 8

echo "[2/2] 启动前端 Vite (localhost:5173/app/)..."
(cd "$FRONTEND" && npm run dev) &
FRONTEND_PID=$!

trap "echo; echo '正在停止...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true" INT TERM EXIT

echo
echo "=============================================="
echo " 前端: http://localhost:5173/app/"
echo " 后端: http://127.0.0.1:2024"
echo " API 文档: http://127.0.0.1:2024/docs"
echo " Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024"
echo " 按 Ctrl+C 停止全部服务"
echo "=============================================="
echo

wait

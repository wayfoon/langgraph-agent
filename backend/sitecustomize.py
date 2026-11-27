"""
Python 启动钩子 —— 让 uvicorn reload 子进程也输出东八区日志时间。

LangGraph CLI 默认开启热重载，uvicorn 会重新启动一个 Python 解释器。
父进程里的 structlog 补丁不会自动带到子进程，因此在解释器初始化阶段
通过 ``sitecustomize`` 再装一次。只有 ``dev_server.py`` 设置的环境变量
存在时才会生效，普通 Python 命令不会改变日志时区。

本文件会先链式加载环境里原有的 ``sitecustomize``（例如 WorkBuddy 的沙箱
垫片），避免把宿主的启动钩子覆盖掉。

作者：风锋
创建日期：2026-05-27
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def _load_previous_sitecustomize() -> None:
    """按 sys.path 顺序加载除本文件外的第一个 sitecustomize。"""
    if os.getenv("LANGGRAPH_SITECUSTOMIZE_CHAINED") == "1":
        return

    os.environ["LANGGRAPH_SITECUSTOMIZE_CHAINED"] = "1"
    current_file = Path(__file__).resolve()

    for entry in sys.path:
        if not entry:
            continue
        candidate = Path(entry) / "sitecustomize.py"
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved == current_file or not resolved.is_file():
            continue

        spec = importlib.util.spec_from_file_location(
            "_langgraph_previous_sitecustomize", resolved
        )
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return


def _install_log_time_patch() -> None:
    """仅在开发服务器启动时安装东八区日志时间补丁。"""
    if os.getenv("LANGGRAPH_EAST8_LOG_TIME") != "1":
        return

    try:
        from dev_server import install_east_8_log_time

        install_east_8_log_time()
    except Exception as exc:  # 启动钩子不能因为日志补丁失败而阻断服务
        print(f"[warn] 东八区日志时间补丁未生效: {exc}", file=sys.stderr)


_load_previous_sitecustomize()
_install_log_time_patch()

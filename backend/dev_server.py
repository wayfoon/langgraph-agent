"""
LangGraph 开发服务器启动入口 —— 把控制台日志时间固定为东八区。

问题背景
--------
LangGraph API 0.20.x 使用 structlog 输出日志，并在依赖包中硬编码了：

    structlog.processors.TimeStamper(fmt="iso", utc=True)

因此日志时间戳是 UTC，例如 ``2026-05-27T07:12:48.224022Z``。
本机系统时区虽然是东八区，但 ``utc=True`` 会绕过本机时区，日志仍显示 UTC。

处理方式
--------
在 LangGraph CLI 与 uvicorn 配置日志之前，先替换 structlog 的时间戳处理器，
输出带显式 ``+08:00`` 偏移的 ISO 8601 时间，例如
``2026-05-27T15:12:48.224022+08:00``。
uvicorn 的 reload 子进程通过 ``sitecustomize.py`` 应用同一补丁。
只改本项目的启动链路，不改 site-packages，也不改任何截图。

作者：风锋
创建日期：2026-05-27
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import structlog
from structlog.typing import EventDict, WrappedLogger

# 东八区固定偏移。不用本机时区，确保换机器后日志口径一致。
EAST_8 = timezone(timedelta(hours=8), "UTC+08:00")

_INSTALLED = False


class East8TimeStamper:
    """按东八区输出 ISO 8601 日志时间戳。"""

    def __call__(
        self, logger: WrappedLogger, method_name: str, event_dict: EventDict
    ) -> EventDict:
        """把 event_dict 的 timestamp 改写为显式 +08:00 的当前时间。"""
        event_dict["timestamp"] = datetime.now(EAST_8).isoformat()
        return event_dict


_EAST_8_STAMPER = East8TimeStamper()


def _replace_timestamp(processors: list[Any]) -> list[Any]:
    """把处理器链里的 UTC 时间戳处理器替换为东八区版本。"""
    from structlog.processors import TimeStamper

    replaced = False
    for index, processor in enumerate(processors):
        if isinstance(processor, (TimeStamper, East8TimeStamper)):
            processors[index] = _EAST_8_STAMPER
            replaced = True

    # 依赖版本变化导致找不到时间戳处理器时，补一个到最前面，避免静默漏改。
    if not replaced:
        processors.insert(0, _EAST_8_STAMPER)

    return processors


def install_east_8_log_time() -> None:
    """安装东八区日志时间补丁；重复调用是安全的。"""
    global _INSTALLED
    if _INSTALLED:
        return

    # uvicorn reload 会启动新的 Python 进程。通过环境变量 + sitecustomize
    # 让子进程在解释器初始化阶段也装上补丁，热重载后日志时区不会回退。
    backend_root = str(Path(__file__).resolve().parent)
    existing_python_path = os.environ.get("PYTHONPATH", "")
    if backend_root not in existing_python_path.split(os.pathsep):
        os.environ["PYTHONPATH"] = (
            backend_root + os.pathsep + existing_python_path
            if existing_python_path
            else backend_root
        )
    os.environ["LANGGRAPH_EAST8_LOG_TIME"] = "1"

    # 标准 logging 的 asctime 也走本机时间，这里显式固化一次。
    logging.Formatter.converter = time.localtime

    # 导入 langgraph_api.logging 会触发 structlog 的初始配置。
    # 必须在 CLI / uvicorn 创建 Formatter 之前把处理器替换掉。
    from langgraph_api import logging as langgraph_logging

    _replace_timestamp(langgraph_logging.shared_processors)

    config = structlog.get_config()
    configured_processors = list(config.get("processors") or [])
    structlog.configure(processors=_replace_timestamp(configured_processors))

    _INSTALLED = True


def main() -> None:
    """启动开发服务器：先装日志补丁，再交给 LangGraph CLI。"""
    install_east_8_log_time()

    from langgraph_cli.cli import cli

    cli()


if __name__ == "__main__":
    main()

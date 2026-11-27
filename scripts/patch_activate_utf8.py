"""向虚拟环境的激活脚本注入 UTF-8 模式设置。

文件说明
--------
本脚本用于修复中文 Windows 上的编码故障。

问题背景
--------
中文 Windows 的系统 ANSI 代码页是 GBK（cp936），CPython 的默认文本编码跟随区域设置。
而 LangGraph 读取若干 UTF-8 文件时**未指定 encoding**：

* ``site-packages/openapi.json`` —— 见 ``langgraph_api/validation.py``
* ``backend/.env``                   —— 见 ``langgraph_api/cli.py`` 的 ``dotenv.DotEnv``

在 GBK 下读取这两个文件会抛出 ``UnicodeDecodeError``，导致 dev 服务器直接启动失败。
设置 ``PYTHONUTF8=1`` 可让 CPython 进入 UTF-8 模式，一次性解决上述全部读取路径。

为什么需要单独脚本
------------------
``activate.bat`` 属于虚拟环境目录，重建 venv 就会被覆盖。因此把注入动作固化为脚本，
由 ``scripts/setup-venv.bat`` 在重建环境后自动调用。

本脚本是幂等的 —— 重复执行不会产生重复内容。

用法::

    .venv\\Scripts\\python.exe scripts\\patch_activate_utf8.py

作者：风锋
创建日期：2026-03-06
"""

from __future__ import annotations

import pathlib
import sys

# 插入位置标记：activate.bat 末尾的标签行
ANCHOR = ":END"

# 待注入的片段。REM 开头的中文注释说明注入原因，便于后来者理解。
SNIPPET = (
    '\nREM --- LangGraph Agent: force UTF-8 mode -------------------------------------\n'
    "REM On Chinese Windows the ANSI codepage is GBK (cp936). Python's default\n"
    "REM encoding follows the locale, and LangGraph reads UTF-8 files without an\n"
    "REM explicit encoding argument (site-packages/openapi.json, backend/.env),\n"
    "REM which raises UnicodeDecodeError under GBK. UTF-8 mode fixes all of them.\n"
    'set "PYTHONUTF8=1"\n'
    'set "PYTHONIOENCODING=utf-8"\n'
)


def find_activate() -> pathlib.Path:
    """定位当前解释器同级的 ``activate.bat``。

    Returns:
        激活脚本的路径。

    Raises:
        FileNotFoundError: 找不到激活脚本时抛出。
    """
    scripts_dir = pathlib.Path(sys.executable).resolve().parent
    candidate = scripts_dir / "activate.bat"
    if not candidate.exists():
        raise FileNotFoundError(f"activate.bat not found at {candidate}")
    return candidate


def patch(target: pathlib.Path) -> bool:
    """向激活脚本注入 UTF-8 环境变量设置。

    Args:
        target: 激活脚本路径。

    Returns:
        文件被修改返回 True；此前已打过补丁则返回 False。

    Raises:
        ValueError: 脚本中找不到锚点标记时抛出。
    """
    original = target.read_text(encoding="utf-8")

    # 幂等判断：已含该设置则直接跳过
    if "PYTHONUTF8" in original:
        print(f"  already patched, skipping: {target}")
        return False

    if ANCHOR not in original:
        raise ValueError(f"anchor {ANCHOR!r} not found in {target}")

    patched = original.replace(ANCHOR, SNIPPET + "\n" + ANCHOR, 1)
    target.write_text(patched, encoding="utf-8", newline="")
    print(f"  patched: {target}")
    return True


def main() -> int:
    """脚本入口：定位并修补激活脚本。

    Returns:
        进程退出码：成功返回 0，失败返回 1。
    """
    try:
        target = find_activate()
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    try:
        changed = patch(target)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if changed:
        print("  UTF-8 mode enabled for the virtual environment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

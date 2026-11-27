"""命令行方式运行研究Agent —— 快速验证后端能力，无需启动前后端服务。

文件说明
--------
本脚本调用 ``agent.graph`` 中定义的 LangGraph 研究图，以一次性问答的方式执行完整
研究流程，并把最终回答打印到标准输出。



作者：风锋
创建日期：2026-03-06
"""

import argparse

from langchain_core.messages import HumanMessage

from agent.graph import graph
from agent.llm_provider import default_model


def main() -> None:
    """命令行入口：解析参数、执行研究流程、打印最终回答。"""
    parser = argparse.ArgumentParser(description="运行 LangGraph 研究Agent")
    parser.add_argument("question", help="要研究的问题")
    parser.add_argument(
        "--initial-queries",
        type=int,
        default=3,
        help="初始搜索查询数量",
    )
    parser.add_argument(
        "--max-loops",
        type=int,
        default=2,
        help="最大研究轮数",
    )
    parser.add_argument(
        "--reasoning-model",
        default=None,
        help=(
            "生成答案所用模型。"
            "默认跟随当前供应商配置的模型（LLM_MODEL）。"
        ),
    )
    args = parser.parse_args()

    state = {
        "messages": [HumanMessage(content=args.question)],
        "initial_search_query_count": args.initial_queries,
        "max_research_loops": args.max_loops,
    }

    # 只有调用方显式指定了模型才固定下来，否则交由 provider 层解析。
    # 此处若写死模型ID，会静默覆盖 LLM_MODEL，导致所有非 Gemini 供应商全部失效。
    state["reasoning_model"] = args.reasoning_model or default_model()

    result = graph.invoke(state)
    messages = result.get("messages", [])
    if messages:
        print(messages[-1].content)


if __name__ == "__main__":
    main()

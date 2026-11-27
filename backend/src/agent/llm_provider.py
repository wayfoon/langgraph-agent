"""大模型供应商抽象层。

文件说明
--------
本模块是「Gemini Fullstack LangGraph Quickstart」项目的**模型层改造**产物。

改造背景
--------
上游项目把大模型硬编码为 Gemini（``ChatGoogleGenerativeAI``），并在联网检索时
依赖 Google 原生的 ``google_search`` grounding 工具。这两个依赖在
``generativelanguage.googleapis.com`` 被网络策略拦截的环境下完全不可用 ——
而这类环境在国内企业内网中极为普遍。

改造思路
--------
DeepSeek、Moonshot、通义千问（兼容模式）、Ollama 等厂商均支持 OpenAI 兼容协议，
因此本模块对外只暴露一个工厂函数，返回 OpenAI 协议的对话模型。
**换厂商是配置变更，不是代码变更** —— 改 ``backend/.env`` 即可。

环境变量
--------
LLM_PROVIDER:
    供应商标识，取值 ``deepseek``（默认）/ ``openai`` / ``dashscope`` / ``ollama``
LLM_API_KEY:
    当前供应商的 API Key。留空时自动回退到供应商同名的环境变量
LLM_BASE_URL:
    接口地址，覆盖供应商默认地址
LLM_MODEL:
    模型 ID，留空时使用供应商默认模型

作者：风锋
创建日期：2026-03-06
"""

import os

from langchain_core.language_models.chat_models import BaseChatModel

# 各供应商的默认接入参数。DeepSeek 的 OpenAI 兼容接口是本项目的主目标。
_PROVIDER_DEFAULTS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-flash",
        "env_key": "DEEPSEEK_API_KEY",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "env_key": "OPENAI_API_KEY",
    },
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "env_key": "DASHSCOPE_API_KEY",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "qwen2.5:7b",
        "env_key": "OLLAMA_API_KEY",
    },
}


def _resolve_provider_config() -> dict:
    """解析当前生效的供应商配置。

    读取顺序：显式的 ``LLM_*`` 环境变量优先，其次是供应商默认值。
    ``LLM_PROVIDER`` 填了无法识别的值时回退到 deepseek，避免因配置笔误导致启动失败。

    Returns:
        包含 ``provider`` / ``api_key`` / ``base_url`` / ``model`` 四个键的字典。
    """
    provider = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
    defaults = _PROVIDER_DEFAULTS.get(
        provider, _PROVIDER_DEFAULTS["deepseek"]
    )

    api_key = (
        os.getenv("LLM_API_KEY")
        or os.getenv(defaults["env_key"])
        # 部分 OpenAI 兼容网关虽不校验 Key，但仍要求该参数非空
        or "not-needed"
    )
    base_url = os.getenv("LLM_BASE_URL", defaults["base_url"])
    model = os.getenv("LLM_MODEL", defaults["model"])

    return {
        "provider": provider,
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
    }


def get_llm(
    model: str | None = None,
    temperature: float = 0.0,
    max_retries: int = 2,
) -> BaseChatModel:
    """构造当前配置对应的对话模型实例。

    Args:
        model: 显式指定模型 ID；为 None 时使用供应商默认模型。
        temperature: 采样温度，默认 0 以保证结果可复现。
        max_retries: 瞬时错误（网络抖动、限流）的重试次数。

    Returns:
        遵循 OpenAI chat-completions 协议的 LangChain 对话模型。
    """
    # 延迟导入：langgraph-api 启动时会扫描全部模块，提前导入会拖慢启动
    from langchain_openai import ChatOpenAI

    config = _resolve_provider_config()
    return ChatOpenAI(
        model=model or config["model"],
        temperature=temperature,
        max_retries=max_retries,
        api_key=config["api_key"],
        base_url=config["base_url"],
        timeout=120,
    )


def default_model() -> str:
    """返回当前供应商的默认模型 ID。

    Returns:
        模型 ID 字符串。
    """
    return _resolve_provider_config()["model"]


# 仅支持 ``response_format: {"type": "json_object"}`` 的供应商集合。
# LangChain 默认使用更严格的 ``json_schema`` 模式，DeepSeek 会对其直接报错，
# 因此这些供应商必须显式降级，否则结构化输出在请求阶段才会失败。
_JSON_MODE_ONLY = {"deepseek", "ollama"}


def with_structured_output(llm: BaseChatModel, schema: type) -> object:
    """给对话模型绑定 Pydantic 结构化输出 schema。

    ``json_schema`` 模式更严格、校验更充分，但部分 OpenAI 兼容供应商（DeepSeek
    即是其一）只实现了 ``json_object``。本函数按供应商实际支持的能力选择最严格的
    可用模式，避免把失败推迟到请求发出之后。

    Args:
        llm: 待绑定的对话模型。
        schema: 描述期望输出结构的 Pydantic 模型。

    Returns:
        能产出 ``schema`` 实例的可运行对象。
    """
    provider = _resolve_provider_config()["provider"]
    if provider in _JSON_MODE_ONLY:
        return llm.with_structured_output(schema, method="json_mode")
    return llm.with_structured_output(schema)

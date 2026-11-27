"""联网检索抽象层。

文件说明
--------
本模块是「Gemini Fullstack LangGraph Quickstart」项目的**检索层改造**产物。

改造背景
--------
上游项目调用 Gemini 原生的 ``google_search`` grounding 工具，并从响应中读取
``grounding_metadata``。该接口是 Google 私有能力，且其域名在多数企业网络被拦截，
直接照搬会导致整条研究链路无法执行。

改造思路
--------
本模块以「bing 抓取 / tavily API / gemini 原生」三种后端重新实现同一份契约。
所有后端统一返回 :class:`SearchResult` 列表，再交由大模型生成引用 ——
**引用仍由模型产出，而非字符串拼接**，因此前端无需任何改动。

检索后端
--------
bing:
    抓取 Bing 公开结果页，免 API Key
tavily:
    Tavily Search 官方接口，需要 ``TAVILY_API_KEY``
gemini:
    上游原生 Google Search grounding，需要 ``GEMINI_API_KEY``

作者：风锋
创建日期：2026-03-06
"""

from __future__ import annotations

import html
import hashlib
import os
import re
import urllib.parse
from dataclasses import dataclass
from typing import List

# 引用短 ID 的前缀。回答正文中嵌入该前缀 + 哈希，指向具体来源。
SHORT_URL_PREFIX = "https://research.local/id/"


@dataclass
class SearchResult:
    """单条联网检索结果。

    Attributes:
        title: 页面标题，用于展示与生成引用。
        url: 页面的规范地址，即引用的跳转目标。
        snippet: 从页面提取的文本摘要，作为模型的溯源素材。
    """

    title: str
    url: str
    snippet: str


def _clean(text: str) -> str:
    """清洗 HTML 文本：剥离标签、反转义实体、合并空白。

    Args:
        text: 含 HTML 标签的原始文本。

    Returns:
        纯文本结果，多余空白已压缩为单个空格。
    """
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _search_bing(query: str, max_results: int) -> List[SearchResult]:
    """抓取 Bing 公开结果页并解析。

    该后端免 API Key，是本项目在受限网络下的默认选择。依赖 Bing 结果页的
    HTML 结构，若对方改版可能导致解析失效 —— 此时切换 tavily 后端即可。

    Args:
        query: 搜索关键词。
        max_results: 返回结果条数上限。

    Returns:
        解析出的检索结果；页面结构变化时可能返回空列表。
    """
    import httpx

    url = "https://cn.bing.com/search?" + urllib.parse.urlencode(
        {"q": query, "count": max_results}
    )
    # 伪装成常规浏览器，避免被识别为爬虫而返回验证页
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    results: List[SearchResult] = []
    with httpx.Client(timeout=30, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
        page = response.text

    # 每条结果位于 <li class="b_algo"> 块内
    for block in re.findall(r'<li class="b_algo".*?</li>', page, re.S):
        link = re.search(
            r'<h2>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S
        )
        if not link:
            continue
        href, raw_title = link.group(1), link.group(2)
        title = _clean(raw_title)
        # 过滤掉相对路径等无效链接
        if not href.startswith("http"):
            continue

        snippet = ""
        body = re.search(
            r'<p[^>]*class="[^"]*b_lineclamp[^"]*"[^>]*>(.*?)</p>', block, re.S
        )
        if body:
            snippet = _clean(body.group(1))
        else:
            # 取不到摘要时退回标题，至少保证有可用素材
            snippet = title

        results.append(SearchResult(title=title, url=href, snippet=snippet))
        if len(results) >= max_results:
            break

    return results


def _search_tavily(query: str, max_results: int) -> List[SearchResult]:
    """调用 Tavily Search 官方接口。

    Args:
        query: 搜索关键词。
        max_results: 返回结果条数上限。

    Returns:
        解析出的检索结果。

    Raises:
        ValueError: 未配置 ``TAVILY_API_KEY`` 时抛出。
    """
    import httpx

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError("TAVILY_API_KEY is required for the tavily search backend")

    response = httpx.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()

    return [
        SearchResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            snippet=(item.get("content") or "")[:1500],
        )
        for item in payload.get("results", [])
    ][:max_results]


def _search_gemini(query: str, max_results: int) -> List[SearchResult]:
    """使用 Gemini 原生的 Google Search grounding。

    保留该后端是为了在 ``GEMINI_API_KEY`` 可用且 Google 可达时维持上游行为。

    Args:
        query: 搜索关键词。
        max_results: 返回结果条数上限。

    Returns:
        解析出的检索结果。
    """
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=os.getenv("GEMINI_SEARCH_MODEL", "gemini-2.0-flash"),
        contents=query,
        config={"tools": [{"google_search": {}}], "temperature": 0},
    )

    results: List[SearchResult] = []
    grounding = getattr(response.candidates[0], "grounding_metadata", None)
    if not grounding:
        return results

    for chunk in getattr(grounding, "grounding_chunks", []) or []:
        web = getattr(chunk, "web", None)
        if web is None:
            continue
        results.append(
            SearchResult(
                title=getattr(web, "title", "") or "",
                url=getattr(web, "uri", "") or "",
                snippet="",
            )
        )
        if len(results) >= max_results:
            break

    return results


# 检索后端注册表，键为 SEARCH_BACKEND 的合法取值
_BACKENDS = {
    "bing": _search_bing,
    "tavily": _search_tavily,
    "gemini": _search_gemini,
}


def search(query: str, max_results: int = 5) -> List[SearchResult]:
    """使用当前配置的检索后端执行一次联网搜索。

    后端选择顺序：
      1. 显式设置 ``SEARCH_BACKEND`` 环境变量；
      2. 自动探测 —— 配了 ``TAVILY_API_KEY`` 用 tavily，否则用 bing。

    Args:
        query: 搜索关键词。
        max_results: 返回结果条数上限。

    Returns:
        检索结果列表；无可用结果时返回空列表。

    Raises:
        ValueError: ``SEARCH_BACKEND`` 取了无法识别的值时抛出。
    """
    backend = os.getenv("SEARCH_BACKEND", "").strip().lower()
    if not backend:
        backend = "tavily" if os.getenv("TAVILY_API_KEY") else "bing"

    handler = _BACKENDS.get(backend)
    if handler is None:
        raise ValueError(
            f"Unknown SEARCH_BACKEND '{backend}'. "
            f"Available: {', '.join(sorted(_BACKENDS))}"
        )

    try:
        results = handler(query, max_results)
    except Exception as exc:  # noqa: BLE001 - 降级返回空结果，不中断整轮研究
        print(f"[search] backend '{backend}' failed for '{query}': {exc}")
        return []

    return results[:max_results]


def build_short_urls(
    results: List[SearchResult], search_id: int
) -> dict[str, str]:
    """为每条结果生成稳定的引用短 ID。

    上游实现用自增序号作短 ID，在并发研究分支命中同一页面时会撞号 ——
    两个不同分支会拿到同一个短 ID，最终生成答案时就会把错误的 URL 填进引用。
    改用 URL 哈希后，短 ID 具备确定性且不会冲突。

    Args:
        results: 单次查询的检索结果。
        search_id: 查询标识，保留用于调试。

    Returns:
        原始 URL 到短 URL 的映射字典。
    """
    mapping: dict[str, str] = {}
    for result in results:
        if result.url not in mapping:
            digest = hashlib.md5(result.url.encode("utf-8")).hexdigest()[:10]
            mapping[result.url] = f"{SHORT_URL_PREFIX}{digest}"
    return mapping


def format_for_prompt(results: List[SearchResult]) -> str:
    """把检索结果渲染为投喂给大模型的溯源素材。

    Args:
        results: 单次查询的检索结果。

    Returns:
        可直接嵌入提示词的文本块，每条结果一段。
    """
    if not results:
        return "(no search results found)"

    blocks = []
    for idx, result in enumerate(results):
        blocks.append(
            f"[{idx + 1}] {result.title}\n"
            f"URL: {result.url}\n"
            f"Content: {result.snippet}"
        )
    return "\n\n".join(blocks)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from langgraph.graph import add_messages
from typing_extensions import Annotated


import operator


def _dedupe_by_url(
    left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """Merge two source lists, keeping one entry per distinct URL.

    The upstream project appends every search hit to ``sources_gathered`` with a
    plain ``operator.add`` reducer. Because parallel research branches often
    retrieve the same page, the resulting list contains duplicates. This reducer
    keeps the first occurrence of each URL and preserves order.

    Args:
        left: The accumulated sources so far.
        right: The sources produced by the current node.

    Returns:
        The merged, de-duplicated list.
    """
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    for bucket in (left or [], right or []):
        for source in bucket:
            url = source.get("value") or source.get("short_url")
            if url in seen:
                continue
            seen.add(url)
            merged.append(source)

    return merged


class OverallState(TypedDict):
    messages: Annotated[list, add_messages]
    search_query: Annotated[list, operator.add]
    web_research_result: Annotated[list, operator.add]
    sources_gathered: Annotated[list, _dedupe_by_url]
    initial_search_query_count: int
    max_research_loops: int
    research_loop_count: int
    reasoning_model: str


class ReflectionState(TypedDict):
    is_sufficient: bool
    knowledge_gap: str
    follow_up_queries: Annotated[list, operator.add]
    research_loop_count: int
    number_of_ran_queries: int


class Query(TypedDict):
    query: str
    rationale: str


class QueryGenerationState(TypedDict):
    search_query: list[Query]


class WebSearchState(TypedDict):
    search_query: str
    id: str


@dataclass(kw_only=True)
class SearchStateOutput:
    running_summary: str = field(default=None)  # Final report

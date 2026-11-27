import os

from agent.tools_and_schemas import SearchQueryList, Reflection
from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langgraph.types import Send
from langgraph.graph import StateGraph
from langgraph.graph import START, END
from langchain_core.runnables import RunnableConfig

from agent.state import (
    OverallState,
    QueryGenerationState,
    ReflectionState,
    WebSearchState,
)
from agent.configuration import Configuration
from agent.prompts import (
    get_current_date,
    query_writer_instructions,
    web_searcher_instructions,
    reflection_instructions,
    answer_instructions,
)
from agent.llm_provider import get_llm, with_structured_output
from agent.search import (
    build_short_urls,
    format_for_prompt,
    search,
)
from agent.utils import (
    get_research_topic,
)

load_dotenv()


def _source_label(title: str) -> str:
    """Derive a short, readable label for a cited source.

    The upstream implementation used ``title.split(".")[:-1][0]``, which drops
    the domain suffix. That crashes on titles without a dot, so the fallback
    chain here keeps the title usable in every case.

    Args:
        title: The raw page title.

    Returns:
        A label suitable for the citation markdown link.
    """
    if not title:
        return "source"
    stripped = title.split(".")[0].strip()
    return (stripped or title)[:80]

# Provider configuration is validated lazily so the server can boot even when
# only one of the keys is present. See agent/llm_provider.py.
if not (
    os.getenv("LLM_API_KEY")
    or os.getenv("DEEPSEEK_API_KEY")
    or os.getenv("OPENAI_API_KEY")
    or os.getenv("DASHSCOPE_API_KEY")
    or os.getenv("GEMINI_API_KEY")
):
    raise ValueError(
        "No LLM credentials found. Set LLM_API_KEY (or DEEPSEEK_API_KEY / "
        "OPENAI_API_KEY / DASHSCOPE_API_KEY) in backend/.env"
    )


# Nodes
def generate_query(state: OverallState, config: RunnableConfig) -> QueryGenerationState:
    """LangGraph node that generates search queries based on the User's question.

    Uses the configured LLM to create an optimized set of search queries for
    web research based on the User's question.

    Args:
        state: Current graph state containing the User's question
        config: Configuration for the runnable, including LLM provider settings

    Returns:
        Dictionary with state update, including search_query key containing the generated queries
    """
    configurable = Configuration.from_runnable_config(config)

    # check for custom initial search query count
    if state.get("initial_search_query_count") is None:
        state["initial_search_query_count"] = configurable.number_of_initial_queries

    llm = get_llm(
        model=configurable.query_generator_model or None,
        temperature=1.0,
        max_retries=2,
    )
    structured_llm = with_structured_output(llm, SearchQueryList)

    # Format the prompt
    current_date = get_current_date()
    formatted_prompt = query_writer_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
        number_queries=state["initial_search_query_count"],
    )
    # Generate the search queries
    result = structured_llm.invoke(formatted_prompt)

    # Models sometimes return more queries than requested. Each extra query
    # spawns another parallel web research branch, so cap it to keep both the
    # latency and the token spend bounded.
    limit = max(1, int(state["initial_search_query_count"]))
    queries = [q for q in (result.query or []) if q and q.strip()][:limit]
    if not queries:
        queries = [get_research_topic(state["messages"])]

    return {"search_query": queries}


def continue_to_web_research(state: QueryGenerationState):
    """LangGraph node that sends the search queries to the web research node.

    This is used to spawn n number of web research nodes, one for each search query.
    """
    return [
        Send("web_research", {"search_query": search_query, "id": int(idx)})
        for idx, search_query in enumerate(state["search_query"])
    ]


def web_research(state: WebSearchState, config: RunnableConfig) -> OverallState:
    """LangGraph node that performs web research using a pluggable search backend.

    The upstream implementation calls Gemini's native ``google_search`` grounding
    tool and reads ``grounding_metadata`` off the response. That API is
    Google-only. This implementation instead:

      1. Retrieves raw results from the configured search backend.
      2. Feeds those results back to the LLM, which writes the summary and
         cites sources using the ``[label](short_url)`` markdown format.

    The output contract is identical to the original, so downstream nodes and
    the frontend need no changes.

    Args:
        state: Current graph state containing the search query and research loop count
        config: Configuration for the runnable, including search API settings

    Returns:
        Dictionary with state update, including sources_gathered, research_loop_count, and web_research_results
    """
    configurable = Configuration.from_runnable_config(config)

    query = state["search_query"]
    try:
        search_id = int(state["id"])
    except (TypeError, ValueError):
        search_id = 0

    # Step 1 -- retrieve raw web results.
    results = search(query, max_results=configurable.search_result_count)
    if not results:
        return {
            "sources_gathered": [],
            "web_research_result": [
                f"No search results were found for '{query}'."
            ],
        }

    # Step 2 -- short ids keep the answer tokens small; the final answer node
    # swaps them back to the original URLs.
    short_url_map = build_short_urls(results, search_id)

    grounding = format_for_prompt(results)
    formatted_prompt = (
        web_searcher_instructions.format(
            current_date=get_current_date(),
            research_topic=query,
        )
        + "\n\nSearch Results:\n"
        + grounding
        + "\n\nCitation Rules (MUST FOLLOW):\n"
        "- Cite every factual claim with the matching source number, using markdown format.\n"
        "- The citation URL must be the short id shown below, NOT the original URL.\n"
        "- Available short ids:\n"
        + "\n".join(
            f"  [{idx + 1}] -> {short_url_map[result.url]}"
            + (f"  ({result.title})" if result.title else "")
            for idx, result in enumerate(results)
            if result.url in short_url_map
        )
        + "\n"
    )

    # Step 3 -- let the LLM synthesize the summary with citations.
    llm = get_llm(
        model=configurable.query_generator_model or None,
        temperature=0,
        max_retries=2,
    )
    response = llm.invoke(formatted_prompt)
    modified_text = response.content if isinstance(response.content, str) else str(
        response.content
    )

    sources_gathered = []
    for result in results:
        short_url = short_url_map.get(result.url)
        if not short_url:
            continue
        sources_gathered.append(
            {
                "label": _source_label(result.title),
                "short_url": short_url,
                "value": result.url,
            }
        )

    return {
        "sources_gathered": sources_gathered,
        # NOTE: the upstream implementation also wrote the query back into
        # "search_query". Because that channel uses an appending reducer, the
        # list grew to twice its length and the "number of queries run"
        # counter drifted. The queries are already recorded by generate_query,
        # so the research branch does not need to write them again.
        "web_research_result": [modified_text],
    }


def reflection(state: OverallState, config: RunnableConfig) -> ReflectionState:
    """LangGraph node that identifies knowledge gaps and generates potential follow-up queries.

    Analyzes the current summary to identify areas for further research and generates
    potential follow-up queries. Uses structured output to extract
    the follow-up query in JSON format.

    Args:
        state: Current graph state containing the running summary and research topic
        config: Configuration for the runnable, including LLM provider settings

    Returns:
        Dictionary with state update, including search_query key containing the generated follow-up query
    """
    configurable = Configuration.from_runnable_config(config)
    # Increment the research loop count and get the reasoning model
    state["research_loop_count"] = state.get("research_loop_count", 0) + 1
    reasoning_model = state.get("reasoning_model", configurable.reflection_model)

    # Format the prompt
    current_date = get_current_date()
    formatted_prompt = reflection_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
        summaries="\n\n---\n\n".join(state["web_research_result"]),
    )
    # init Reasoning Model
    llm = get_llm(
        model=reasoning_model or None,
        temperature=1.0,
        max_retries=2,
    )
    result = with_structured_output(llm, Reflection).invoke(formatted_prompt)

    # Bound the follow-up fan-out: each query spawns another search branch.
    max_follow_ups = max(1, configurable.number_of_initial_queries)
    follow_ups = [
        q for q in (result.follow_up_queries or []) if q and q.strip()
    ][:max_follow_ups]

    return {
        "is_sufficient": result.is_sufficient,
        "knowledge_gap": result.knowledge_gap,
        "follow_up_queries": follow_ups,
        "research_loop_count": state["research_loop_count"],
        "number_of_ran_queries": len(state["search_query"]),
    }


def evaluate_research(
    state: ReflectionState,
    config: RunnableConfig,
) -> OverallState:
    """LangGraph routing function that determines the next step in the research flow.

    Controls the research loop by deciding whether to continue gathering information
    or to finalize the summary based on the configured maximum number of research loops.

    Args:
        state: Current graph state containing the research loop count
        config: Configuration for the runnable, including max_research_loops setting

    Returns:
        String literal indicating the next node to visit ("web_research" or "finalize_summary")
    """
    configurable = Configuration.from_runnable_config(config)
    max_research_loops = (
        state.get("max_research_loops")
        if state.get("max_research_loops") is not None
        else configurable.max_research_loops
    )
    if state["is_sufficient"] or state["research_loop_count"] >= max_research_loops:
        return "finalize_answer"

    follow_ups = [
        q for q in (state.get("follow_up_queries") or []) if q and q.strip()
    ]
    if not follow_ups:
        # Nothing to research further -- finalize rather than spawn empty work.
        return "finalize_answer"

    base_id = int(state.get("number_of_ran_queries") or 0)
    return [
        Send(
            "web_research",
            {
                "search_query": follow_up_query,
                "id": base_id + idx,
            },
        )
        for idx, follow_up_query in enumerate(follow_ups)
    ]


def finalize_answer(state: OverallState, config: RunnableConfig):
    """LangGraph node that finalizes the research summary.

    Prepares the final output by deduplicating and formatting sources, then
    combining them with the running summary to create a well-structured
    research report with proper citations.

    Args:
        state: Current graph state containing the running summary and sources gathered

    Returns:
        Dictionary with state update, including running_summary key containing the formatted final summary with sources
    """
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = state.get("reasoning_model") or configurable.answer_model

    # Format the prompt
    current_date = get_current_date()
    formatted_prompt = answer_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
        summaries="\n---\n\n".join(state["web_research_result"]),
    )

    # init the answer model
    llm = get_llm(
        model=reasoning_model or None,
        temperature=0,
        max_retries=2,
    )
    result = llm.invoke(formatted_prompt)

    # Replace the short urls with the original urls and add all used urls to the sources_gathered
    unique_sources = []
    for source in state["sources_gathered"]:
        if source["short_url"] in result.content:
            result.content = result.content.replace(
                source["short_url"], source["value"]
            )
            unique_sources.append(source)

    return {
        "messages": [AIMessage(content=result.content)],
        "sources_gathered": unique_sources,
    }


# Create our Agent Graph
builder = StateGraph(OverallState, config_schema=Configuration)

# Define the nodes we will cycle between
builder.add_node("generate_query", generate_query)
builder.add_node("web_research", web_research)
builder.add_node("reflection", reflection)
builder.add_node("finalize_answer", finalize_answer)

# Set the entrypoint as `generate_query`
# This means that this node is the first one called
builder.add_edge(START, "generate_query")
# Add conditional edge to continue with search queries in a parallel branch
builder.add_conditional_edges(
    "generate_query", continue_to_web_research, ["web_research"]
)
# Reflect on the web research
builder.add_edge("web_research", "reflection")
# Evaluate the research
builder.add_conditional_edges(
    "reflection", evaluate_research, ["web_research", "finalize_answer"]
)
# Finalize the answer
builder.add_edge("finalize_answer", END)

graph = builder.compile(name="pro-search-agent")

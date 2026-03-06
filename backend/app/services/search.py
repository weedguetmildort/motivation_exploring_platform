"""Search agent service using OpenAI tool calling + DuckDuckGo."""

import json
from ddgs import DDGS
from openai import OpenAI

# Tool schema for OpenAI function calling
_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for current information. "
            #"Use this when you need facts, news, or anything that may have changed recently. "
            "Input: a concise search query string. "
            "Output: numbered list of results with title, URL, and snippet."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A concise search query string.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Number of results to return (default 5, max 10).",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
}


def _run_search(query: str, max_results: int = 5) -> tuple[str, list[dict]]:
    """Execute a DuckDuckGo search and return (formatted_text, raw_results)."""
    max_results = min(max_results, 10)
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))

    if not results:
        return "No results found.", []

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r['title']}")
        lines.append(f"    URL: {r['href']}")
        lines.append(f"    {r['body']}")
        lines.append("")
    return "\n".join(lines), results


def get_chat_response_with_search(
    client: OpenAI,
    model: str,
    messages: list[dict],
) -> dict[str, str | list]:
    """Run an agentic search loop.

    The model decides when to call web_search. After all tool calls finish,
    the model writes its final answer with inline markdown citations.

    Returns:
        {"reply": str, "citations": list[{"n": int, "title": str, "url": str}]}
    """
    accumulated_results: list[dict] = []

    # Append citation instruction to system message
    system = next((m for m in messages if m["role"] == "system"), None)
    citation_instruction = (
        " When citing sources, embed them as inline markdown links: "
        "[source title](url). Cite directly in the sentence, not at the end."
    )
    if system:
        patched_messages = [
            {**system, "content": system["content"] + citation_instruction},
            *[m for m in messages if m["role"] != "system"],
        ]
    else:
        patched_messages = [
            {"role": "system", "content": citation_instruction.strip()},
            *messages,
        ]

    loop_messages = list(patched_messages)

    for _ in range(5):  # max 5 search iterations
        response = client.chat.completions.create(
            model=model,
            messages=loop_messages,
            tools=[_SEARCH_TOOL],
            tool_choice="auto",
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            break

        # Execute each tool call and feed results back
        loop_messages.append(msg)
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments)
            formatted, raw = _run_search(
                query=args["query"],
                max_results=args.get("max_results", 5),
            )
            accumulated_results.extend(raw)
            loop_messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": formatted,
            })
    else:
        # Exhausted iterations — get final answer without tools
        response = client.chat.completions.create(
            model=model,
            messages=loop_messages,
        )
        msg = response.choices[0].message

    reply_text = (msg.content or "").strip()

    # Deduplicate and number citations from all search results
    seen: dict[str, int] = {}
    citations: list[dict] = []
    for r in accumulated_results:
        url = r["href"]
        if url not in seen:
            seen[url] = len(seen) + 1
            citations.append({"n": seen[url], "title": r["title"], "url": url})

    return {"reply": reply_text, "citations": citations}

"""
The agentic layer. Claude is given a search_knowledge_base tool and
decides for itself whether a question needs retrieval, how to phrase
the query, whether to search docs, logs, or both, and when to
reformulate and try again versus just answering.

Requires ANTHROPIC_API_KEY in the environment.
"""

import os

import anthropic

from rag.retriever import Retriever

MODEL = "claude-sonnet-4-6"
MAX_TOOL_ROUNDS = 4  # caps the retrieve -> evaluate -> reformulate loop

ENABLE_WEB_SEARCH = os.environ.get("RAG_ENABLE_WEB_SEARCH", "false").lower() == "true"
WEB_SEARCH_MAX_USES = 3

SYSTEM_PROMPT = """You are the research assistant embedded in the Space Signal \
Receiver project (a SETI-style radio signal detection pipeline). You have a \
search_knowledge_base tool covering two kinds of sources:
  - "doc": research papers, SETI/radio-astronomy references and tutorials \
the project owner has actually added
  - "log": this project's own run outputs - detections, drift-search \
results, waterfall plot summaries

Some chunks are text extracted from PDFs/Word docs; others are captions \
Claude vision generated from uploaded images (waterfall plots, \
spectrograms) at ingest time - both are searched and cited the same way.

## Decision process
For every question, first decide: can this be answered confidently from \
general knowledge, or does it need specific facts from the knowledge base?

If retrieval is needed:
1. Formulate a precise search query - rephrase the user's question for \
retrieval rather than passing it through verbatim.
2. Choose source_type "doc", "log", or leave unset to search both.
3. After seeing results, judge whether they actually answer the question. \
If not, reformulate (different phrasing, or split into sub-questions) and \
search again - you have a few attempts before you should tell the user you \
couldn't find enough information rather than guessing.
4. If the question has multiple parts, consider searching separately for \
each part rather than combining them into one query.

## Answering rules
- Ground every specific claim (numbers, drift rates, detection results, \
paper findings) in retrieved content, and cite the source file after the \
claim, e.g. (source: waterfall_run_042.json).
- Be explicit when you're answering from general knowledge instead of \
retrieved content.
- If doc and log results conflict, or a log result doesn't match what the \
docs would predict, say so rather than picking one silently.
- If nothing relevant turns up after a few tries, say that plainly.
"""

WEB_SEARCH_PROMPT_ADDENDUM = """

## Web search
You also have a web_search tool for anything outside this project's own \
indexed docs/logs and outside your general knowledge - current events, a \
paper you don't have indexed, or anything you should verify rather than \
recall. Prefer search_knowledge_base first for anything about this \
project's own work; reach for web_search when the knowledge base doesn't \
cover it or the question needs current information. Cite web sources the \
same way the tool already does (it auto-cites at the end of your turn).
"""

TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": (
            "Search the project's indexed documents and logs. Returns the "
            "top matching chunks with their source filename."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A precise search query, rephrased for retrieval.",
                },
                "source_type": {
                    "type": "string",
                    "enum": ["doc", "log"],
                    "description": "Restrict to research docs or to this project's own logs. Omit to search both.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of chunks to retrieve (default 5).",
                },
            },
            "required": ["query"],
        },
    }
]

if ENABLE_WEB_SEARCH:
    TOOLS.append(
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": WEB_SEARCH_MAX_USES,
        }
    )
    SYSTEM_PROMPT += WEB_SEARCH_PROMPT_ADDENDUM


class RAGAgent:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.retriever = Retriever()

    def _run_tool(self, tool_input: dict) -> list[dict]:
        return self.retriever.search(
            query=tool_input["query"],
            top_k=tool_input.get("top_k", 5),
            source_type=tool_input.get("source_type"),
        )

    def ask(self, user_message: str) -> dict:
        """Returns {"answer": str, "sources": [source filenames used]}."""
        messages = [{"role": "user", "content": user_message}]
        sources_used = set()

        for _ in range(MAX_TOOL_ROUNDS):
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            # web_search results (if the tool is enabled) show up as
            # web_search_tool_result blocks - already resolved server-side,
            # just collect their URLs for the sources list.
            for block in response.content:
                if block.type != "web_search_tool_result":
                    continue
                results = block.content if isinstance(block.content, list) else []
                for r in results:
                    url = r.get("url") if isinstance(r, dict) else getattr(r, "url", None)
                    if url:
                        sources_used.add(f"web: {url}")

            if response.stop_reason == "pause_turn":
                # A long server-tool (web_search) sequence paused - just
                # continue the turn with the accumulated content.
                messages.append({"role": "assistant", "content": response.content})
                continue

            if response.stop_reason != "tool_use":
                answer = "".join(
                    block.text for block in response.content if block.type == "text"
                )
                return {"answer": answer, "sources": sorted(sources_used)}

            messages.append({"role": "assistant", "content": response.content})

            # Only search_knowledge_base needs a client-side tool_result -
            # web_search is executed and resolved by the API automatically.
            tool_results = []
            for block in response.content:
                if block.type != "tool_use" or block.name != "search_knowledge_base":
                    continue
                results = self._run_tool(block.input)
                for r in results:
                    sources_used.add(r["source"])
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": [{"type": "text", "text": _format_results(results)}],
                    }
                )
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

        # Hit the round cap without a final answer - ask once more without tools.
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT
            + "\n\nYou have used up your search attempts. Answer with what you "
            "found, or say plainly that you couldn't find enough information.",
            messages=messages,
        )
        answer = "".join(block.text for block in response.content if block.type == "text")
        return {"answer": answer, "sources": sorted(sources_used)}


def _format_results(results: list[dict]) -> str:
    if not results:
        return "No matching chunks found."
    lines = []
    for r in results:
        lines.append(f"[{r['source_type']}: {r['source']}] {r['text']}")
    return "\n\n".join(lines)

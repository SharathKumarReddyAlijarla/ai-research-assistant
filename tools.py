"""
tools.py

This file defines the tools the LangChain agent can call.
Each tool is a normal Python function decorated with @tool so LangChain can
discover it, read its docstring, and call it when needed.

Why each library is needed:
- datetime: add a timestamp when saving output to file.
- pathlib.Path: safe and clear path/file handling.
- wikipedia: fetch topic summaries from Wikipedia.
- duckduckgo_search.DDGS: perform web searches.
- langchain.tools.tool: turn functions into LangChain tools.
"""

from datetime import datetime
from pathlib import Path

import wikipedia
from duckduckgo_search import DDGS
from langchain.tools import tool


@tool
def search_tool(query: str) -> str:
    """
    Search the web using DuckDuckGo and return top results.

    Why needed:
    - LLM knowledge can be outdated.
    - This tool gives fresher external information.
    """
    try:
        # Open a DDGS search client and request up to 5 text results.
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))

        if not results:
            return "No web results found."

        # Convert raw result objects into a readable multi-line string.
        # This makes it easier for the model to cite and summarize results.
        formatted_results = []
        for idx, item in enumerate(results, start=1):
            title = item.get("title", "No title")
            url = item.get("href") or item.get("url") or "No URL"
            snippet = item.get("body", "")
            formatted_results.append(
                f"{idx}. {title}\nURL: {url}\nSnippet: {snippet}"
            )
        return "\n\n".join(formatted_results)
    except Exception as exc:
        # Return errors as text so the agent can continue instead of crashing.
        return f"Search failed: {exc}"


@tool
def wiki_tool(query: str) -> str:
    """
    Fetch a short Wikipedia summary for a topic.

    Why needed:
    - Wikipedia is useful for quick definitions and background context.
    - The agent can combine this with search results for better answers.
    """
    try:
        # Grab a short summary to keep context compact.
        return wikipedia.summary(query, sentences=3, auto_suggest=True, redirect=True)
    except wikipedia.DisambiguationError as exc:
        # If the title matches many pages, return options to refine the query.
        options = ", ".join(exc.options[:5])
        return f"Query is ambiguous. Try one of: {options}"
    except wikipedia.PageError:
        # Page does not exist for the provided query.
        return "No matching Wikipedia page found."
    except Exception as exc:
        # Non-fatal error path for network/library issues.
        return f"Wikipedia lookup failed: {exc}"


@tool
def save_tool(data: str, filename: str = "research_output.txt") -> str:
    """
    Save text output to a local file.

    Why needed:
    - Lets the agent persist results for later use.
    - Keeps a timestamped record of generated research.
    """
    # Keep only the file name part to avoid writing outside current folder
    # when a path is accidentally provided.
    safe_name = Path(filename).name
    output_path = Path.cwd() / safe_name

    # Write a simple report header + timestamp + tool data.
    output_path.write_text(
        f"Research Output\nTimestamp: {datetime.now()}\n\n{data}",
        encoding="utf-8",
    )
    # Return location so the agent/user knows where the file was written.
    return f"Saved to {output_path}"

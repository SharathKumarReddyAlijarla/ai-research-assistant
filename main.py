"""
main.py

This file runs a command-line research assistant.
The user types a research question, the agent may call tools (web search, wiki, save),
and the program prints a strict JSON response with:
- topic
- summary
- sources
- tools_used

Why each library is needed:
- os: read environment variables like API keys and model names.
- python-dotenv (load_dotenv): load values from .env into environment variables.
- pydantic (BaseModel): define and validate the exact output structure.
- langchain_openai / langchain_anthropic: chat model clients.
- langchain_core.output_parsers (PydanticOutputParser): parse model text into
  the Pydantic schema.
- langchain.agents (create_agent): build an agent that can call tools.
- tools.py imports: custom tool functions that the agent can use.
"""

import os
from dotenv import load_dotenv
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import PydanticOutputParser
from langchain.agents import create_agent
from tools import search_tool, wiki_tool, save_tool


def _extract_text_from_response(response: dict) -> str:
    """
    LangChain v1 agents return a dictionary with a "messages" list.
    The final assistant answer is usually in the last message.

    This helper normalizes different content shapes:
    - plain string content
    - list of content parts (for multimodal/message-part formats)

    We need this because the parser expects one plain text string.
    """
    messages = response.get("messages", [])
    if not messages:
        # If the response has no messages, return empty text to avoid crashes.
        return ""

    content = messages[-1].content
    if isinstance(content, str):
        # Most common case: assistant content is already plain text.
        return content
    if isinstance(content, list):
        # Some providers return content as a list of typed parts.
        # Keep only text parts and join them into one string.
        chunks = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                chunks.append(part.get("text", ""))
        return "\n".join(chunk for chunk in chunks if chunk).strip()
    # Fallback: convert unknown content types to string instead of failing.
    return str(content)


def _build_llm():
    """
    Choose which LLM provider to use based on available API keys.

    Priority:
    1) Anthropic if ANTHROPIC_API_KEY exists
    2) OpenAI if OPENAI_API_KEY exists

    Model names can be overridden via .env:
    - ANTHROPIC_MODEL
    - OPENAI_MODEL
    """
    if os.getenv("ANTHROPIC_API_KEY"):
        # Default model is set to one known to work with this account setup.
        anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        return ChatAnthropic(model=anthropic_model)
    if os.getenv("OPENAI_API_KEY"):
        openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        return ChatOpenAI(model=openai_model)
    # No provider key found -> fail fast with a clear setup message.
    raise RuntimeError(
        "No API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY in your environment/.env."
    )


# Load .env values into process environment.
# This lets os.getenv(...) read keys and model overrides.
load_dotenv()


# Define the exact JSON structure we want from the assistant.
# Pydantic validates the response and helps catch format mistakes.
class ResearchResponse(BaseModel):
    topic: str
    summary: str
    sources: list[str]
    tools_used: list[str]


# Parser that converts model text output into ResearchResponse.
parser = PydanticOutputParser(pydantic_object=ResearchResponse)


def _create_research_agent():
    """
    Build a LangChain agent with:
    - selected LLM
    - available tools
    - system instructions enforcing strict JSON format

    The format instructions come from PydanticOutputParser so the model knows
    exactly what schema to return.
    """
    llm = _build_llm()
    tools = [search_tool, wiki_tool, save_tool]
    return create_agent(
        model=llm,
        tools=tools,
        system_prompt=(
            "You are a research assistant that helps generate a research paper. "
            "Use tools when necessary. "
            "Return only valid output in the exact format below and nothing else:\n"
            f"{parser.get_format_instructions()}"
        ),
    )


def main() -> None:
    # Create the agent. If keys are missing, print setup message and exit.
    try:
        agent = _create_research_agent()
    except RuntimeError as exc:
        print(exc)
        return

    # 1) Ask the user for a research topic.
    # 2) Send the query as a chat message to the agent.
    query = input("What can I help you research? ")
    try:
        raw_response = agent.invoke({"messages": [{"role": "user", "content": query}]})
    except Exception as exc:
        error_text = str(exc)
        # Give a friendlier message for one common configuration issue:
        # model id exists in code but not in the user's Anthropic account access.
        if "not_found_error" in error_text and "model:" in error_text:
            configured_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
            print(
                f"Configured Anthropic model '{configured_model}' was not found. "
                "Set ANTHROPIC_MODEL in .env to a model your key can access."
            )
            return
        # For all other runtime issues, print a generic failure message.
        print(f"Agent call failed: {exc}")
        return

    # Convert LangChain response object into plain text we can parse.
    final_text = _extract_text_from_response(raw_response)

    # Parse model output into the strict schema and print pretty JSON.
    try:
        structured_response = parser.parse(final_text)
        print(structured_response.model_dump_json(indent=2))
    except Exception as e:
        # If parsing fails, print error and raw response to help debugging.
        print(f"Error parsing response: {e}")
        print(f"Raw response: {raw_response}")


# Standard Python entry point:
# run main() only when this file is executed directly.
if __name__ == "__main__":
    main()

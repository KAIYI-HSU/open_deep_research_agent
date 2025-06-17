"""Run the graph workflow with human plan approval.

This script follows the steps in `src/open_deep_research/graph.ipynb`.
It compiles the graph, runs until the planning interrupt, and allows the
user to approve or revise the plan before continuing to generate the
final report.
"""

import asyncio
import getpass
import os
import uuid

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from open_deep_research.graph import builder

REPORT_STRUCTURE = """Use this structure to create a report on the user-provided topic:

1. Introduction (no research needed)
   - Brief overview of the topic area

2. Main Body Sections:
   - Each section should focus on a sub-topic of the user-provided topic

3. Conclusion
   - Aim for 1 structural element (either a list of table) that distills the main body sections
   - Provide a concise summary of the report"""


def _set_env(var: str) -> None:
    """Prompt for an environment variable if it is missing."""
    if not os.environ.get(var):
        os.environ[var] = getpass.getpass(f"{var}: ")


async def main() -> None:
    """Execute the graph with an interactive plan review step."""
    memory = MemorySaver()
    graph = builder.compile(checkpointer=memory)

    for var in [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "TAVILY_API_KEY",
        "GROQ_API_KEY",
        "PERPLEXITY_API_KEY",
    ]:
        _set_env(var)

    thread = {
        "configurable": {
            "thread_id": str(uuid.uuid4()),
            "search_api": "tavily",
            "planner_provider": "openai",
            "planner_model": "o3",
            "writer_provider": "openai",
            "writer_model": "o3",
            "max_search_depth": 2,
            "report_structure": REPORT_STRUCTURE,
        }
    }

    topic = input("Enter report topic: ")

    data = {"topic": topic}
    command = None

    while True:
        stream = graph.astream(data if command is None else command, thread, stream_mode="updates")
        async for event in stream:
            if "__interrupt__" in event:
                print(event["__interrupt__"][0].value)  # noqa: T201
                feedback = input("Pass 'true' to approve or provide feedback: ")
                resume_val = True if feedback.strip().lower() == "true" else feedback.strip()
                command = Command(resume=resume_val)
                break
        else:
            break
        data = None

    final_state = graph.get_state(thread)
    report = final_state.values.get("final_report", "No report generated")

    print("\n===== Final Report =====\n")  # noqa: T201
    print(report)  # noqa: T201


if __name__ == "__main__":
    asyncio.run(main())

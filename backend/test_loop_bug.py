import asyncio
from unittest.mock import MagicMock
import app.core.auto_execution_loop.loop as loop_module
from app.core.auto_execution_loop.loop import run_auto_execution_loop
import logging

logging.basicConfig(level=logging.INFO)

async def mock_run_executor(*args, **kwargs):
    async def mock_stream():
        # Simulate LLM getting cut off mid-tag
        yield "<think>\nthinking...\n</think>\n\n<search"
    return mock_stream()

async def main():
    loop_module.run_executor = mock_run_executor
    
    # Mock tool handler
    tool_handler = MagicMock()
    tool_handler.tool_results = []
    
    res, summary, esc = await run_auto_execution_loop(
        user_input="test",
        instruction="test",
        search_results="",
        memory_text="",
        tool_handler=tool_handler,
        mode="chat"
    )
    print("FINAL RESULT:", repr(res))

if __name__ == "__main__":
    asyncio.run(main())

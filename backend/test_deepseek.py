import asyncio
import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

async def main():
    client = AsyncOpenAI(
        api_key=os.environ.get("DEEPSEEK_API_KEY", "sk-ac763202bbee4db795beadc9eb72f50d"),
        base_url="https://api.deepseek.com/v1"
    )
    
    stream = await client.chat.completions.create(
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": "How are you?"}],
        stream=True
    )
    
    async for chunk in stream:
        delta = chunk.choices[0].delta
        reasoning = getattr(delta, "reasoning_content", None)
        content = getattr(delta, "content", None)
        print(f"reasoning: {reasoning!r}, content: {content!r}")

if __name__ == "__main__":
    asyncio.run(main())

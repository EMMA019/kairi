import re

with open('d:/program/chat/backend/app/core/llm_client.py', 'r', encoding='utf-8') as f:
    content = f.read()

if "from app.core.usage_tracker" not in content:
    content = content.replace(
        "from app.utils.logger import get_logger",
        "from app.utils.logger import get_logger\nfrom app.core.usage_tracker import check_budget, record_usage\nfrom fastapi import HTTPException\nimport tiktoken"
    )

# Rename existing functions
content = content.replace('async def call_model(', 'async def _call_model_inner(')
content = content.replace('async def stream_model(', 'async def _stream_model_inner(')

# Append wrappers at the end
wrappers = """

def _estimate_tokens(text: str) -> int:
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 2

async def call_model(
    system_instruction: str,
    messages: list,
    model_name: str | None = None,
    max_tokens: int = 16384,
    provider: str | None = None,
    temperature: float = 0.7,
) -> str:
    if not check_budget():
        raise HTTPException(status_code=429, detail="API utilization limit (daily budget) exceeded. Please try again tomorrow.")
        
    prompt_text = system_instruction + "".join([m.get("content", "") for m in messages])
    prompt_tokens = _estimate_tokens(prompt_text)
    
    result = await _call_model_inner(system_instruction, messages, model_name, max_tokens, provider, temperature)
    
    completion_tokens = _estimate_tokens(result)
    actual_model = model_name or "default-model"
    record_usage(actual_model, prompt_tokens, completion_tokens)
    
    return result

async def stream_model(
    system_instruction: str,
    messages: list,
    model_name: str | None = None,
    max_tokens: int = 16384,
    provider: str | None = None,
    temperature: float = 0.7,
):
    if not check_budget():
        yield "【エラー】本日のAPI利用上限に達しました。明日またお試しください。"
        return
        
    prompt_text = system_instruction + "".join([m.get("content", "") for m in messages])
    prompt_tokens = _estimate_tokens(prompt_text)
    
    completion_text = ""
    async for chunk in _stream_model_inner(system_instruction, messages, model_name, max_tokens, provider, temperature):
        completion_text += chunk
        yield chunk
        
    completion_tokens = _estimate_tokens(completion_text)
    actual_model = model_name or "default-model"
    record_usage(actual_model, prompt_tokens, completion_tokens)
"""

content += wrappers

with open('d:/program/chat/backend/app/core/llm_client.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("llm_client.py patched successfully.")

import re

with open('d:/program/chat/backend/app/core/supervisor.py', 'r', encoding='utf-8') as f:
    content = f.read()

orig_loader = """def get_supervisor_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'supervisor_prompt.md')
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"Failed to load supervisor_prompt.md: {e}")
        return "あなたは沈黙AIの「思考・監督モデル」です。ユーザーへの回答は直接行わず、JSON形式のみを出力してください。"
"""

new_loader = """def get_supervisor_system_prompt(category: str = "general") -> str:
    import os
    base_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts')
    
    prompt = ""
    # Base prompt
    prompt_path = os.path.join(base_dir, 'supervisor_prompt.md')
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt += f.read().strip() + "\\n\\n"
    except Exception as e:
        logger.error(f"Failed to load supervisor_prompt.md: {e}")
        return "あなたは沈黙AIの「思考・監督モデル」です。ユーザーへの回答は直接行わず、JSON形式のみを出力してください。"

    # Domain specific rules
    if category == "finance":
        cat_file = "supervisor_prompt_finance.md"
    elif category == "coding":
        cat_file = "supervisor_prompt_coding.md"
    elif category == "travel":
        cat_file = "supervisor_prompt_travel.md"
    else:
        cat_file = None
        
    if cat_file:
        try:
            with open(os.path.join(base_dir, cat_file), 'r', encoding='utf-8') as f:
                prompt += f.read().strip() + "\\n\\n"
        except FileNotFoundError:
            pass

    return prompt.strip()
"""

content = content.replace(orig_loader, new_loader)


orig_run_supervisor_sig = """async def run_supervisor(
    user_input: str,
    search_results: str | None,
    memory_text: str | None,
    history_messages: list[dict],
    mode: str = "chat",
    system_instruction: str = "",
) -> tuple[dict[str, Any], str]:"""

new_run_supervisor_sig = """async def run_supervisor(
    user_input: str,
    search_results: str | None,
    memory_text: str | None,
    history_messages: list[dict],
    mode: str = "chat",
    system_instruction: str = "",
    category: str = "general",
) -> tuple[dict[str, Any], str]:"""

content = content.replace(orig_run_supervisor_sig, new_run_supervisor_sig)


orig_call_loader = """    final_system_prompt = get_supervisor_system_prompt()"""
new_call_loader = """    final_system_prompt = get_supervisor_system_prompt(category)"""

content = content.replace(orig_call_loader, new_call_loader)

with open('d:/program/chat/backend/app/core/supervisor.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("supervisor.py patched.")

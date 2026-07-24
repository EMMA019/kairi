import os
import re

file_path = 'd:/program/chat/backend/app/core/supervisor.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the SUPERVISOR_SYSTEM_PROMPT block with a dynamic loader function
pattern = re.compile(r'SUPERVISOR_SYSTEM_PROMPT\s*=\s*\"\"\"(.*?)\"\"\"', re.DOTALL)
replacement = '''import os

def get_supervisor_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'supervisor_prompt.md')
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"Failed to load supervisor_prompt.md: {e}")
        return "あなたは沈黙AIの「思考・監督モデル」です。ユーザーへの回答は直接行わず、JSON形式のみを出力してください。"'''

content = pattern.sub(replacement, content, count=1)

# Now find where SUPERVISOR_SYSTEM_PROMPT is used and replace it with get_supervisor_system_prompt()
content = content.replace('final_system_prompt = SUPERVISOR_SYSTEM_PROMPT', 'final_system_prompt = get_supervisor_system_prompt()')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("supervisor.py patched successfully.")

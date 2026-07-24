import os
import re

file_path = 'd:/program/chat/backend/app/core/supervisor.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

pattern = re.compile(r'SUPERVISOR_SYSTEM_PROMPT\s*=\s*\"\"\"(.*?)\"\"\"', re.DOTALL)
match = pattern.search(content)
if match:
    prompt_content = match.group(1)
    
    os.makedirs('d:/program/chat/backend/app/prompts', exist_ok=True)
    with open('d:/program/chat/backend/app/prompts/supervisor_prompt.md', 'w', encoding='utf-8') as f:
        f.write(prompt_content.strip())
        
    print('Prompt extracted successfully.')
else:
    print('Pattern not found.')

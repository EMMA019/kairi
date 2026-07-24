import re

with open('d:/program/chat/backend/app/core/auto_execution_loop.py', 'r', encoding='utf-8') as f:
    content = f.read()

orig = '''                    supervisor_result = await _analyze_with_supervisor(
                        escalation_history=escalation_history,
                        user_input=user_input,
                        instruction=instruction,
                        supervisor_sys_prompt=supervisor_sys_prompt,
                        supervisor_dynamic_sys=supervisor_dynamic_sys,
                        mode=mode,
                        history_messages=history_messages,
                        yield_sse_func=yield_sse_func,
                    )'''

new = '''                    supervisor_result = await _analyze_with_supervisor(
                        escalation_history=escalation_history,
                        user_input=user_input,
                        instruction=instruction,
                        supervisor_sys_prompt=supervisor_sys_prompt,
                        supervisor_dynamic_sys=supervisor_dynamic_sys,
                        mode=mode,
                        history_messages=history_messages,
                        yield_sse_func=yield_sse_func,
                        category="coding" if is_coding_task else "general",
                    )'''

content = content.replace(orig, new)

orig_def = '''async def _analyze_with_supervisor(
    escalation_history: list[dict],
    user_input: str,
    instruction: str,
    supervisor_sys_prompt: str,
    supervisor_dynamic_sys: str,
    mode: str,
    history_messages: list[dict],
    yield_sse_func,
) -> str | None:'''

new_def = '''async def _analyze_with_supervisor(
    escalation_history: list[dict],
    user_input: str,
    instruction: str,
    supervisor_sys_prompt: str,
    supervisor_dynamic_sys: str,
    mode: str,
    history_messages: list[dict],
    yield_sse_func,
    category: str = "general",
) -> str | None:'''

content = content.replace(orig_def, new_def)

orig_run = '''        supervisor_json, reasoning = await run_supervisor(
            user_input=user_input + "\\n\\n" + analysis_prompt + "\\n\\n" + supervisor_dynamic_sys,
            search_results=None,
            memory_text=None,
            history_messages=history_messages,
            mode=mode,
            system_instruction=supervisor_sys_prompt,
        )'''

new_run = '''        supervisor_json, reasoning = await run_supervisor(
            user_input=user_input + "\\n\\n" + analysis_prompt + "\\n\\n" + supervisor_dynamic_sys,
            search_results=None,
            memory_text=None,
            history_messages=history_messages,
            mode=mode,
            system_instruction=supervisor_sys_prompt,
            category=category,
        )'''

content = content.replace(orig_run, new_run)


with open('d:/program/chat/backend/app/core/auto_execution_loop.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('auto_execution_loop.py patched')

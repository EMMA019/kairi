import re

with open('d:/program/chat/backend/app/routers/chat.py', 'r', encoding='utf-8') as f:
    content = f.read()

orig_search_plan = '''        search_plan = await plan_search(user_input, messages)
        search_needed = search_plan["needs_search"] or request.force_search
        search_queries = search_plan.get("search_queries", [])'''

new_search_plan = '''        search_plan = await plan_search(user_input, messages)
        search_needed = search_plan["needs_search"] or request.force_search
        search_queries = search_plan.get("search_queries", [])
        chat_category = search_plan.get("category", "general")'''

content = content.replace(orig_search_plan, new_search_plan)

orig_run_supervisor = '''                    supervisor_json, reasoning = await run_supervisor(
                        user_input=current_user_input_with_context + "\\n\\n【動的システムコンテキスト】\\n" + supervisor_dynamic_sys,
                        search_results=search_results_text,
                        memory_text=filtered_kv_text,
                        history_messages=messages,
                        mode=mode,
                        system_instruction=supervisor_sys_prompt,
                    )'''

new_run_supervisor = '''                    supervisor_json, reasoning = await run_supervisor(
                        user_input=current_user_input_with_context + "\\n\\n【動的システムコンテキスト】\\n" + supervisor_dynamic_sys,
                        search_results=search_results_text,
                        memory_text=filtered_kv_text,
                        history_messages=messages,
                        mode=mode,
                        system_instruction=supervisor_sys_prompt,
                        category=chat_category,
                    )'''

content = content.replace(orig_run_supervisor, new_run_supervisor)

with open('d:/program/chat/backend/app/routers/chat.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('chat.py patched')

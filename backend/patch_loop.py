import re

with open('d:/program/chat/backend/app/core/auto_execution_loop.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Modify executed_tool_signatures check around line 464
orig_check = """                if not has_error:
                    tag_match = re.search(r'<(mcp_call|search|read_url)[^>]*>', stream_response)
                    sig = tag_match.group(0) if tag_match else None
                    if sig and sig in executed_tool_signatures:
                        logger.warning(f"🛑 同一ツール呼び出しの重複検出により無限ループをシャットダウンします: {sig}")
                        final_accumulated_response += stream_response + "\\n\\n" + "\\n\\n".join(tool_handler.tool_results)
                        break
                    if sig:
                        executed_tool_signatures.add(sig)"""

new_check = """                if not has_error:
                    # 変更: 全てのツールタグ（run_command, file, replace等も）を対象に重複チェック
                    tag_match = re.search(r'<(mcp_call|search|read_url|read_file|list_dir|run_command|file|replace)[^>]*>(.*?)</\\1>', stream_response, re.DOTALL)
                    if not tag_match:
                        tag_match = re.search(r'<(mcp_call|search|read_url|read_file|list_dir|run_command|file|replace)[^>]*/>', stream_response)
                    
                    sig = tag_match.group(0) if tag_match else None
                    if sig and sig in executed_tool_signatures:
                        logger.warning(f"🛑 同一ツール呼び出しの重複検出により無限ループをシャットダウンします: {sig[:100]}...")
                        final_accumulated_response += stream_response + "\\n\\n*[無限ループ検知のため中断しました]*\\n" + "\\n\\n".join(tool_handler.tool_results)
                        break
                    if sig:
                        executed_tool_signatures.add(sig)"""

content = content.replace(orig_check, new_check)

with open('d:/program/chat/backend/app/core/auto_execution_loop.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("auto_execution_loop.py patched successfully.")

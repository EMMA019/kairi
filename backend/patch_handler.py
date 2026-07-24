import re
import os

with open('d:/program/chat/backend/app/core/tools/handler.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add backup utility functions
backup_imports_and_funcs = """
import shutil
import datetime
from pathlib import Path

def _create_backup(filepath: str, workspace_dir: str):
    try:
        if not os.path.exists(filepath):
            return
        backup_dir = os.path.join(workspace_dir, ".backup")
        os.makedirs(backup_dir, exist_ok=True)
        filename = os.path.basename(filepath)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"{filename}_{timestamp}.bak")
        shutil.copy2(filepath, backup_path)
        logger.info(f"🛡️ Backup created: {backup_path}")
    except Exception as e:
        logger.warning(f"Failed to create backup for {filepath}: {e}")

"""
# Append imports near the top
content = content.replace("import re\n", "import re\n" + backup_imports_and_funcs)

# 2. Patch _handle_file_creations to create backup
orig_creation_logic = """                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                with open(abs_path, 'w', encoding='utf-8') as f:
                    f.write(file_content)"""

new_creation_logic = """                _create_backup(abs_path, str(BASE_WORKSPACE_DIR))
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                with open(abs_path, 'w', encoding='utf-8') as f:
                    f.write(file_content)"""

content = content.replace(orig_creation_logic, new_creation_logic)

# 3. Patch _handle_file_replacements to create backup
orig_replace_logic = """                with open(abs_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)"""

new_replace_logic = """                _create_backup(abs_path, str(BASE_WORKSPACE_DIR))
                with open(abs_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)"""

content = content.replace(orig_replace_logic, new_replace_logic)


# 4. Patch _handle_docker_tools for dangerous commands
orig_run_command = """                    cmd = match.group(1).strip()
                    # サプライチェーン攻"""

new_run_command = """                    cmd = match.group(1).strip()
                    
                    # 危険コマンドの事前ブロック
                    dangerous_patterns = [r'^rm\s+-rf\s+/', r'^rm\s+-rf\s+\*', r'^sudo\s+']
                    is_dangerous = False
                    for dp in dangerous_patterns:
                        if re.search(dp, cmd):
                            is_dangerous = True
                            break
                    if is_dangerous:
                        blocked_msg = f"🛡️ Security Block: Command '{cmd}' is blocked for safety reasons."
                        logger.warning(blocked_msg)
                        self.tool_results.append(blocked_msg)
                        events.append({"type": "chunk", "content": f"\\n\\n*[{blocked_msg}]*\\n\\n"})
                        current_response = current_response.replace(match.group(0), f"\\n\\n*[{blocked_msg}]*\\n\\n")
                        continue
                    
                    # サプライチェーン攻"""

content = content.replace(orig_run_command, new_run_command)


with open('d:/program/chat/backend/app/core/tools/handler.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("handler.py patched successfully.")

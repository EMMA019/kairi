import logging
import hashlib
import re
from typing import Dict, List, Tuple, Optional
from src.services.patch_service import PatchService

logger = logging.getLogger("Healer")

class HealerService:
    def __init__(self, fast_client, healer_client):
        self.fast = fast_client     # L1/L2 (DeepSeek/Qwen)
        self.healer = healer_client # L3 (DeepSeek/Qwen)
        self.patcher = PatchService()
        self.repair_history = {} 

    def build_context(self, files: Dict[str, str]) -> str:
        context = []
        for name, content in files.items():
            snippet = content[:1000] + "\n...(truncated)..." if len(content) > 1000 else content
            context.append(f"File: {name}\n```\n{snippet}\n```")
        return "\n".join(context)

    def heal(self, fname: str, content: str, errors: List[str], context_files: Dict, kit: Optional[Dict] = None) -> Tuple[bool, str, str]:
        error_msg = errors[0] if errors else "Unknown error"
        
        # --- ループ検知 ---
        error_hash = hashlib.md5(error_msg.encode('utf-8')).hexdigest()
        history_key = f"{fname}:{error_hash}"
        current_tries = self.repair_history.get(history_key, 0)
        
        if current_tries >= 3:
            logger.warning(f"🛑 Healing Loop Detected for {fname}. Giving up.")
            return False, content, "Loop_GivenUp"
        
        self.repair_history[history_key] = current_tries + 1

        # --- ★強化ポイント: 特定ライブラリへの「強制介入」ロジック ---
        specific_hints = []
        
        # 1. Matplotlibのフリーズ対策
        if "matplotlib" in content or "plt." in content:
            specific_hints.append("CRITICAL: Docker environment detected.")
            specific_hints.append(" - Use `matplotlib.use('Agg')` BEFORE importing pyplot.")
            specific_hints.append(" - Remove `plt.show()`.")
            
        # 2. ネットワーク接続対策
        if "ConnectionRefused" in error_msg:
            specific_hints.append("Hint: If testing network, start a dummy server in a thread.")

        # 3. ★ライブラリ欠損の自動修復 (ModuleNotFoundError)
        # エラー文から不足しているモジュール名を抽出して、インストール指示を出す
        missing_module_match = re.search(r"No module named '([^']+)'", error_msg)
        if missing_module_match:
            missing_lib = missing_module_match.group(1)
            specific_hints.append(f"CRITICAL: Missing library '{missing_lib}'.")
            specific_hints.append(f"You MUST add this line at the VERY TOP of the code:")
            specific_hints.append(f"pip_install('{missing_lib}')")
            specific_hints.append(f"(Note: `pip_install` is a built-in function in this environment. Do not define it.)")

        hint_str = "\n".join(specific_hints)

        base_prompt = f"""
        Fix code in '{fname}'.
        Error: {error_msg}
        
        {hint_str}
        
        Current Code:
        {content}
        """

        logger.info(f"❤️‍🩹 Healing attempt {current_tries+1} for {fname}...")
        
        try:
            prompt_l3 = base_prompt + "\nRewrite the FULL file correctly. Output ONLY the code block inside ```python ... ```."
            fixed_res = self.healer.generate(prompt_l3)
            fixed_code = self._clean_code(fixed_res)
            
            if len(fixed_code) > 10: 
                return True, fixed_code, "DeepSeek_Rewrite"
        except Exception as e:
            logger.error(f"Healer failed: {e}")

        return False, content, "Failed"

    def _clean_code(self, text):
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        blocks = re.findall(r"```python\s*(.*?)```", text, re.DOTALL)
        if blocks:
            return max(blocks, key=len).strip()
        text = text.replace("```python", "").replace("```", "").strip()
        return text
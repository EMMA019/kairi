import json
import re
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger("Architect")

class ArchitectService:
    
    def __init__(self, client, kit_manager):
        self.client = client
        self.kit_manager = kit_manager

    def create_plan(self, user_prompt: str) -> Tuple[List[Dict], Optional[Dict]]:
        """ユーザーの要望とKitに基づいて実装フェーズ計画を作成する"""
        
        matches = self.kit_manager.find_best_match(user_prompt)
        kit = matches[0][0] if matches else None
        
        kit_info = ""
        if kit:
            logger.info(f"🧩 Kit Auto-Selected: {kit.get('name')}")
            tech_stack = ', '.join(kit.get('blueprint', {}).get('suggested_tech_stack', []))
            core_comps = ', '.join(kit.get('blueprint', {}).get('core_components', []))
            kit_info = f"## Active Kit: {kit.get('name')}\nStack: {tech_stack}\nComponents: {core_comps}\n"

        sys_prompt = f"""
        You are a Software Architect.
        Break down the user's request into logical implementation phases.
        
        {kit_info}
        
        # CRITICAL RULES:
        1. **FLEXIBILITY (NEW):** If the user's request explicitly contains terms like "single file", "simple script", "no functions", or "no classes", override the active Kit Blueprint and create only one step: files: ["main.py"].
        2. Separation: UI Logic -> app.py (Streamlit allowed). Data Logic -> *_service.py (NO Streamlit).
        3. Simplicity: Create minimum viable files.
        4. Output JSON Array only.
        """
        
        try:
            response = self.client.generate(f"Request: {user_prompt}", sys_prompt)
            json_str = response.strip()

            # Markdownのコードブロックを除去してJSON抽出
            json_str = re.sub(r"^```json", "", json_str, flags=re.MULTILINE)
            json_str = re.sub(r"^```", "", json_str, flags=re.MULTILINE)
            # DeepSeekの思考プロセス除去
            json_str = re.sub(r"<think>.*?</think>", "", json_str, flags=re.DOTALL).strip()
            
            start_index = json_str.find('[')
            last_index = json_str.rfind(']')
            
            if start_index == -1 or last_index == -1 or start_index > last_index:
                 # フォールバック: JSONが見つからない場合
                 return ([{
                    "phase": "Execution", 
                    "description": f"Implement: {user_prompt}", 
                    "files": ["main.py"]
                 }], kit)

            final_json_data = json_str[start_index : last_index + 1]

            if final_json_data:
                parsed_plan = json.loads(final_json_data)
                cleaned_plan = self._clean_plan_files(parsed_plan)
                return (cleaned_plan, kit) 
            else:
                raise ValueError("Extracted JSON data is empty.")
                
        except Exception as e:
            logger.error(f"Planning failed: {e}. Attempting fallback.")
            
            # フォールバックプラン
            fallback_plan = [{
                "phase": "1", 
                "description": f"Implement the user request: {user_prompt}", 
                "files": ["main.py"]
            }]
            
            cleaned_fallback = self._clean_plan_files(fallback_plan)
            return (cleaned_fallback, kit) 
            
    def _clean_plan_files(self, plan: List[Dict]) -> List[Dict]:
        """LLMの出力ゆらぎを吸収して正規化するメソッド"""
        cleaned_plan = []
        for step in plan:
            if not isinstance(step, dict): continue
                
            # 1. 'description' の正規化
            for k in ['objective', 'summary', 'desc', 'overview', 'goal']:
                if k in step and 'description' not in step:
                    step['description'] = step.pop(k)

            # 2. 'phase' の正規化
            for k in ['phase_title', 'phase_name', 'name', 'step_name', 'title']:
                if k in step and 'phase' not in step:
                    step['phase'] = step.pop(k)

            # 3. 'files' の正規化
            known_file_keys = ['target_files', 'files_to_modify', 'file_list', 'modified_files', 'files_to_create', 'code_files', 'output_files']
            for k in known_file_keys:
                if k in step and 'files' not in step:
                    step['files'] = step.pop(k)

            # 4. キーが見つからない場合のヒューリスティック検索
            if 'files' not in step:
                for v in step.values():
                    if isinstance(v, list) and v and isinstance(v[0], str) and (v[0].endswith('.py') or v[0].endswith('.txt')):
                        step['files'] = v
                        break
                    if isinstance(v, list) and v and isinstance(v[0], dict) and ('filename' in v[0] or 'name' in v[0]):
                        cleaned_files = []
                        for f_dict in v:
                            if 'filename' in f_dict: cleaned_files.append(f_dict['filename'])
                            elif 'name' in f_dict: cleaned_files.append(f_dict['name'])
                        step['files'] = cleaned_files
                        break

            # 5. ファイルリストの中身を文字列に統一
            raw_files = step.get('files', [])
            final_files = []
            for f in raw_files:
                if isinstance(f, dict):
                    if 'filename' in f: final_files.append(f['filename'])
                    elif 'name' in f: final_files.append(f['name'])
                elif isinstance(f, str):
                    final_files.append(f)
            
            step['files'] = final_files

            if 'phase' not in step: step['phase'] = "Phase X"
            if 'description' not in step: step['description'] = "Task Execution"

            cleaned_plan.append(step)
            
        return cleaned_plan
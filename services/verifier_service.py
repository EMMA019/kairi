import ast
import logging
import autopep8
import os
from typing import Dict, List, Set

logger = logging.getLogger("Verifier")

class VerifierService:
    """
    Evo OSの免疫システム。
    v1.5 (Docker Hybrid) 用に制限を緩和。
    OS操作やネットワーク通信はDocker側で隔離されているため、コード上では許可する。
    """
    def __init__(self, runtime=None):
        self.runtime = runtime
        
        self.BANNED_MODULES = {
            # 'os', 'subprocess', 'shutil', 'sys',  <-- 解禁済み
            # 'socket', 'requests', 'urllib',      <-- 解禁済み
            'pickle', 'dill',           # 信頼できないデータのデシリアライズは危険なので一応禁止
            'importlib', '__import__'   # 検証逃れの動的インポートは禁止
        }
        
        # DeepSeek対応: 'exit'と'quit'を禁止リストから削除。
        # コンテナ内での終了は安全な動作であるため。
        self.BANNED_FUNCTIONS = ['eval', 'exec', 'input'] 

    def format_code(self, code: str, filename: str) -> str:
        try:
            if filename.endswith(".py"):
                return autopep8.fix_code(code, options={'aggressive': 1})
            return code.strip() + "\n"
        except: return code

    def verify(self, code: str, filename: str, context_files: dict = None) -> dict:
        ext = os.path.splitext(filename)[1].lower()
        
        if ext == '.py':
            try:
                tree = ast.parse(code)
            except SyntaxError as e:
                return {"valid": False, "errors": [f"Python Syntax: {e}"]}
            
            # A. セキュリティチェック (Immunity Check)
            sec = self._check_banned_nodes(tree)
            if not sec['valid']:
                return sec
            
        return {"valid": True, "errors": []}

    def _check_banned_nodes(self, tree):
        """ASTを走査して『隠しナイフ』を持っていないか検査する"""
        for node in ast.walk(tree):
            # 1. Import 禁止
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split('.')[0] in self.BANNED_MODULES:
                        return {"valid":False, "errors":[f"🚫 Security Alert: Banned import '{a.name}'"]}
            
            # 2. ImportFrom 禁止
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split('.')[0] in self.BANNED_MODULES:
                    return {"valid":False, "errors":[f"🚫 Security Alert: Banned import '{node.module}'"]}
            
            # 3. 関数呼び出し禁止
            elif isinstance(node, ast.Call):
                func_name = None
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                
                if func_name in self.BANNED_FUNCTIONS:
                    return {"valid":False, "errors":[f"🚫 Security Alert: Banned function '{func_name}'"]}
                    
        return {"valid": True, "errors": []}
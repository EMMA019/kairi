import logging

logger = logging.getLogger("EvoQA")

class QualityAssuranceService:
    def __init__(self, client):
        self.client = client # Healerと同じ賢いモデル(Flash/DeepSeek)推奨

    def audit_and_fix(self, project_files: dict) -> str:
        """
        最終監査: ファイル間の不整合（Importミス、関数引数不一致）のみをチェックする。
        DeepSeekなどのローカルLLMがハルシネーション（嘘のバグ報告）をしないよう、
        プロンプトで厳格に制約をかける。
        """
        context_str = self._build_lightweight_context(project_files)
        if not context_str: return ""
        
        system_prompt = """
        Role: Senior QA Engineer (Anti-Hallucination Mode).
        Task: Audit file consistency across the project.
        
        # STRICT RULES (DO NOT VIOLATE):
        1. **Interface Only:** Check ONLY imports and function calls between files. DO NOT audit logic inside functions.
        2. **No Hallucinations:** Do NOT invent bugs. If the code looks 99% correct, output NOTHING.
        3. **Existing Files Only:** Do NOT suggest importing files that do not exist in the provided context.
        4. **Syntax Check:** Only fix critical syntax errors (e.g., missing indentation, unclosed brackets).
        5. **Ignore Style:** Do NOT fix PEP8 or formatting issues.
        
        # Target Issues:
        - ImportError (Module not found in context)
        - AttributeError (Function/Class not defined in target file)
        - NameError (Using undefined variables across files)

        Output Format:
        - If NO critical integration bugs found: Output NOTHING (Empty String).
        - If CRITICAL bug found: Output the FULL corrected file content using:
          # FILENAME: path/to/file.py
          ```python
          ... code ...
          ```
        """
        
        user_prompt = f"Audit these file interfaces and fix ONLY broken links/imports:\n\n{context_str}"

        try:
            # 賢いモデルで一発で決める
            response = self.client.generate(user_prompt, system_prompt)
            
            # 応答が短すぎる、またはコードブロックがない場合は「修正なし」とみなす
            if "```" not in response and len(response) < 50:
                return ""
            
            return response
        except Exception as e:
            logger.error(f"Audit failed: {e}")
            return ""

    def _build_lightweight_context(self, project_files):
        # コンテキストサイズ削減: 
        # コードの中身を全部渡すのではなく、構造を渡すべきだが、
        # 修正させるためにはコードが必要。
        # 妥協案: 主要なコードファイルのみ渡し、巨大なデータファイルやConfigは除外する。
        
        valid_exts = {'.py', '.js', '.html', '.css'}
        content = []
        
        for fname, code in project_files.items():
            if any(fname.endswith(ext) for ext in valid_exts):
                # 20000文字を超えるような巨大ファイルは、先頭と末尾だけ渡す等の工夫
                if len(code) > 20000: 
                    snippet = code[:2000] + f"\n... (truncated {len(code)-4000} chars) ...\n" + code[-2000:]
                else:
                    snippet = code
                content.append(f"# FILENAME: {fname}\n```\n{snippet}\n```")
        
        return "\n".join(content)
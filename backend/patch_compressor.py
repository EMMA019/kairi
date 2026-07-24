import re

with open('d:/program/chat/backend/app/core/context_compressor.py', 'r', encoding='utf-8') as f:
    content = f.read()

orig_instruction = '''    system_instruction = (
        "あなたはAIアシスタントのコンテキスト圧縮モジュールです。\\n"
        "以下の古い会話履歴を読み、ユーザーの「投資方針」「関心のある銘柄」「設定した前提条件」「議論の主要な結論」などの重要な事実（ファクト）を必ず保持したまま、簡潔な要約を作成してください。\\n"
        "細かい挨拶や不要な相槌は省き、後続の会話でAIが文脈を見失わないための「引き継ぎメモ」として箇条書き等で機能するようにしてください。"
    )'''

new_instruction = '''    system_instruction = (
        "あなたはAIアシスタントのコンテキスト圧縮モジュールです。\\n"
        "以下の古い会話履歴を読み、重要な事実（ファクト）を抽出し、以下のJSON形式のみを出力してください。\\n"
        "{\\n"
        "  \\"summary\\": \\"会話全体の簡潔な要約（箇条書き等）\\",\\n"
        "  \\"key_facts\\": [\\n"
        "    {\\"target\\": \\"銘柄名や話題（例：半導体株, 予算）\\", \\"note\\": \\"関連ファクトや方針（例：短期狙いだった, 10万円以内）\\"}\\n"
        "  ]\\n"
        "}\\n"
        "細かい挨拶や不要な相槌は省き、後続の会話でAIが文脈を見失わないための引き継ぎメモを作成してください。"
    )'''

content = content.replace(orig_instruction, new_instruction)


orig_parse = '''    import re
    # DeepSeek Reasoning などの <think> タグを除去する
    summary_result = re.sub(r'<think>.*?</think>', '', summary_result, flags=re.DOTALL).strip()

    summary_text = (
        "【過去の会話の重要コンテキスト要約】\\n"
        f"※これより前に行われた合計{len(old_messages)}ターンの会話の要約です。\\n\\n"
        f"{summary_result}\\n\\n"
        "【要約終了】"
    )'''

new_parse = '''    import re
    import json
    from app.core.kv_store import kv_store

    # DeepSeek Reasoning などの <think> タグを除去する
    summary_result = re.sub(r'<think>.*?</think>', '', summary_result, flags=re.DOTALL).strip()

    # JSON抽出とKV保存
    extracted_summary = summary_result
    try:
        from app.utils.parser import find_json_objects
        objs = find_json_objects(summary_result)
        if objs:
            data = json.loads(objs[0])
            extracted_summary = data.get("summary", extracted_summary)
            key_facts = data.get("key_facts", [])
            for fact in key_facts:
                target = fact.get("target")
                note = fact.get("note")
                if target and note:
                    kv_store.set(target, note)
    except Exception as e:
        logger.error(f"圧縮モジュールのJSONパース/KV保存エラー: {e}")

    summary_text = (
        "【過去の会話の重要コンテキスト要約】\\n"
        f"※これより前に行われた合計{len(old_messages)}ターンの会話の要約です。\\n\\n"
        f"{extracted_summary}\\n\\n"
        "【要約終了】"
    )'''

content = content.replace(orig_parse, new_parse)

with open('d:/program/chat/backend/app/core/context_compressor.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('context_compressor.py patched')

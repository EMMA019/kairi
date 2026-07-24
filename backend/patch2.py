import re

with open('d:/program/chat/backend/app/routers/chat.py', 'r', encoding='utf-8') as f:
    content = f.read()

orig_start = '''    session_id = request.session_id
    user_input = request.message
    mode = request.mode

    # フォローアップ・クールダウン判定'''

new_start = '''    session_id = request.session_id
    user_input = request.message
    mode = request.mode

    if not user_input or not user_input.strip():
        raise HTTPException(status_code=400, detail="メッセージを入力してください。")
    if not session_id:
        raise HTTPException(status_code=400, detail="セッションIDが必要です。")

    # フォローアップ・クールダウン判定'''

content = content.replace(orig_start, new_start)

if 'HTTPException' not in content:
    content = content.replace('from fastapi import APIRouter', 'from fastapi import APIRouter, HTTPException')

content = content.replace(
    'yield _sse_event({"type": "error", "message": str(e)})',
    'yield _sse_event({"type": "error", "message": "システムエラーが発生しました。処理を完了できませんでした。", "detail": str(e)})'
)

with open('d:/program/chat/backend/app/routers/chat.py', 'w', encoding='utf-8') as f:
    f.write(content)

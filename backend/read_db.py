import sqlite3
import json

conn = sqlite3.connect('storage/conversations.db')
cur = conn.cursor()
cur.execute("SELECT content, raw_response, reasoning FROM messages WHERE role='assistant' ORDER BY id DESC LIMIT 5;")
rows = cur.fetchall()
print(json.dumps(rows, ensure_ascii=False, indent=2))

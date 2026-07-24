import re

with open('d:/program/chat/backend/app/core/context_compressor.py', 'r', encoding='utf-8') as f:
    content = f.read()

orig = """    content = re.sub(r'<file path="([^"]+)">\\n([\\s\\S]*?)</file>', _compress_file_tag, content)"""

new = """    content = re.sub(r'<file path="([^"]+)">\\n([\\s\\S]*?)</file>', _compress_file_tag, content)
    
    # 画像（Base64）の圧縮（完全省略）
    content = re.sub(r'<attached_image\\s+filename="([^"]+)"\\s+mime="[^"]+">\\n.*?\\n</attached_image>', r'[Attached Image Omitted: \\1]', content, flags=re.DOTALL)"""

content = content.replace(orig, new)

with open('d:/program/chat/backend/app/core/context_compressor.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('context_compressor.py patched for images')

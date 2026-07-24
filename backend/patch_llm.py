import re

with open('d:/program/chat/backend/app/core/llm_client.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Import tenacity
import_tenacity = """from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type"""

if "import tenacity" not in content and "from tenacity" not in content:
    content = content.replace("import tiktoken\n", f"import tiktoken\n{import_tenacity}\n")

# Decorate _call_model_inner
orig_call_model_inner = """async def _call_model_inner("""

new_call_model_inner = """@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(4),
    retry=retry_if_exception_type(Exception),
    reraise=True
)
async def _call_model_inner("""

if "@retry(" not in content:
    content = content.replace(orig_call_model_inner, new_call_model_inner)


# Decorate _stream_model_inner
orig_stream_model_inner = """async def _stream_model_inner("""

new_stream_model_inner = """@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(4),
    retry=retry_if_exception_type(Exception),
    reraise=True
)
async def _stream_model_inner("""

content = content.replace(orig_stream_model_inner, new_stream_model_inner)

# we need to make sure we don't duplicate if already applied
with open('d:/program/chat/backend/app/core/llm_client.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('llm_client.py patched')

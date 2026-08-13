import asyncio
import re

async def mock_stream(chunks):
    for c in chunks:
        yield c

async def stream_with_newline(original_stream, yield_sse_func=None):
    tag_buf = ""
    in_tag = False
    in_think_block = False
    async for c in original_stream:
        if in_tag:
            tag_buf += c
            if ">" in tag_buf or "\n" in tag_buf:
                match_think = re.search(r'<think\s*>', tag_buf)
                match_end_think = re.search(r'</think\s*>', tag_buf)
                
                if match_think:
                    in_think_block = True
                    remainder = tag_buf[match_think.end():]
                    tag_buf = ""
                    in_tag = False
                    continue
                    
                elif match_end_think:
                    in_think_block = False
                    remainder = tag_buf[match_end_think.end():]
                    tag_buf = ""
                    in_tag = False
                    if remainder:
                        if yield_sse_func:
                            yield_sse_func({"type": "chunk", "content": remainder})
                        yield remainder
                    continue
                    
                elif not re.search(r'<(search|read_url|read_file|run_command|file|replace|list_dir|get_hot_stocks|search_news|mcp_call|escalate)', tag_buf):
                    if not in_think_block:
                        if yield_sse_func:
                            yield_sse_func({"type": "chunk", "content": tag_buf})
                        yield tag_buf
                    tag_buf = ""
                    in_tag = False
                    continue
                else:
                    if not in_think_block:
                        yield tag_buf
                    tag_buf = ""
                    in_tag = False
                    continue
        else:
            if "<" in c:
                in_tag = True
                tag_buf += c
                continue
            else:
                if not in_think_block:
                    if yield_sse_func:
                        yield_sse_func({"type": "chunk", "content": c})
                    yield c
                continue
                
    if tag_buf and not in_tag:
        if not in_think_block:
            if yield_sse_func:
                yield_sse_func({"type": "chunk", "content": tag_buf})
            yield tag_buf
    yield '\n'

async def test_stream(chunks, expected):
    stream = stream_with_newline(mock_stream(chunks))
    result = ""
    async for c in stream:
        result += c
    
    # Assert and print
    print(f"Chunks: {chunks}")
    print(f"Expected: {expected!r}")
    print(f"Got     : {result!r}")
    assert result == expected, f"Failed: {result!r} != {expected!r}"
    print("OK!\n")

async def main():
    print("--- Test 1: No think block ---")
    await test_stream(["hello ", "world"], "hello world\n")
    
    print("--- Test 2: Standard think block ---")
    await test_stream(["<think>\n", "thinking...", "\n</think>\n\n", "answer"], "\n\nanswer\n")
    
    print("--- Test 3: Think block with tool ---")
    await test_stream(["<think>\n", "thinking...", "\n</think>\n\n", "<search query=\"test\" />"], "\n\n<search query=\"test\" />\n")
    
    print("--- Test 4: Chopped chunks ---")
    await test_stream(["<thi", "nk>\nthin", "king\n</t", "hink>\nanswer"], "\nanswer\n")
    
    print("--- Test 5: Tool inside think block (should be hidden) ---")
    await test_stream(["<think>\n", "<search query=\"test\" />", "\n</think>\n\n", "final"], "\n\nfinal\n")
    
    print("--- Test 6: Unclosed think block (simulate cut off) ---")
    await test_stream(["<think>\n", "thinking forever"], "\n")

if __name__ == "__main__":
    asyncio.run(main())

import os
import sys

# Set up path so we can import backend app modules
sys.path.append(os.path.abspath("backend"))

from app.core.fact_filter import verify_actual_vs_guidance_hallucination

source_text = """
Next, capital expenditures. We expect CapEx spend to increase to over $40 billion as we continue to bring more capacity online.
Capital expenditures were $31.9 billion, down sequentially...
"""

test_cases = [
    # Case 1: Hallucination (presenting $40 billion as Q3 actuals)
    "MSFTのQ3実績（2026年1-3月期）四半期Capex：$40 billion超",
    
    # Case 2: Hallucination (presenting $40 billion as actuals with different format)
    "設備投資は $40 billion でした。",
    
    # Case 3: Valid (correctly states it's an outlook/guidance)
    "MSFTのQ4見通し（ガイダンス）はCapex $40 billion超",
    
    # Case 4: Valid (uses the correct actuals number)
    "MSFTのQ3実績はCapex $31.9 billionでした",
]

for i, text in enumerate(test_cases, 1):
    print(f"--- Test Case {i} ---")
    print(f"Input: {text}")
    result = verify_actual_vs_guidance_hallucination(text, source_text=source_text)
    print(f"Result:\n{result}\n")

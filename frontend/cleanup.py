import re

with open('D:/program/chat/frontend/src/components/stocks/Scanner.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove CANSLIM leftovers
content = re.sub(r'const\s+matchCanslim\s*=\s*.*?;\n', '', content)
content = re.sub(r'&&matchCanslim', '', content)
content = re.sub(r'const\s+\[minCanslim,\s*setMinCanslim.*?;\n', '', content)
content = re.sub(r'minCanslim,?', '', content)
content = re.sub(r'setMinCanslim\(0\);', '', content)

# Remove Earnings stuff (FMP)
content = re.sub(r'/\* ══════════════════════════════════════════════════════════\n\s*EARNINGS —.*?══════════════════════════════════════════════════════════ \*/.*?function EarningsBadge.*?\n}\n', '', content, flags=re.DOTALL)
content = re.sub(r'const \[earningsFilter.*?;\n', '', content)
content = re.sub(r'setEarningsFilter\(\'ALL\'\);\s*', '', content)
content = re.sub(r'\{id:\'EARNINGS_SAFE\'.*?\n', '', content)
content = re.sub(r'<span onClick=\{e=>e.stopPropagation\(\)\}>\s*<EarningsBadge ticker=\{t.ticker\}/>\s*</span>', '', content)
content = re.sub(r'TICKER / EARNINGS', 'TICKER', content)
content = re.sub(r'<div>\s*<label.*?// EARNINGS_RISK_FILTER.*?</label>\s*<div.*?>.*?</div>\s*</div>\n', '', content, flags=re.DOTALL)
content = re.sub(r'if\s*\(earningsFilter!==\'ALL\'\).*?}\n', '', content, flags=re.DOTALL)
content = re.sub(r'&&matchEarn', '', content)
content = re.sub(r'earningsFilter,?', '', content)
content = re.sub(r'setEarningsFilter\(\'.*?\'\);?', '', content)

with open('D:/program/chat/frontend/src/components/stocks/Scanner.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

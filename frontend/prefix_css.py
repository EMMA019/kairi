
import os, re

files = ['sentinel.css', 'sentinel-addon.css', 'sentinel-mobile.css', 'sentinel-backtest.css', 'sentinel-weekly.css', 'sentinel-real.css']
for f in files:
    path = os.path.join('src', 'components', 'stocks', f)
    if not os.path.exists(path):
        continue
    with open(path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Very basic regex to prefix rules, skipping media queries and keyframes
    def repl(m):
        p1, p2 = m.group(1), m.group(2)
        if '@media' in p2 or '@keyframes' in p2 or '0%' in p2 or '100%' in p2:
            return m.group(0)
        selectors = p2.split(',')
        new_selectors = []
        for s in selectors:
            s = s.strip()
            if not s or s in ['body', 'html', ':root']:
                new_selectors.append('.stocks-mode-wrapper')
            else:
                new_selectors.append('.stocks-mode-wrapper ' + s)
        return p1 + '\n' + ', '.join(new_selectors) + ' {'
    
    new_content = re.sub(r'(^|\})\s*([^{]+)\{', repl, content)
    with open(path, 'w', encoding='utf-8') as file:
        file.write(new_content)
    print('Prefixed ' + f)


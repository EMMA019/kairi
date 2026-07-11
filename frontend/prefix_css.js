
const fs = require('fs');
const files = ['sentinel.css', 'sentinel-addon.css', 'sentinel-mobile.css', 'sentinel-backtest.css', 'sentinel-weekly.css', 'sentinel-real.css'];
files.forEach(file => {
  const path = './src/components/stocks/' + file;
  if (!fs.existsSync(path)) return;
  let content = fs.readFileSync(path, 'utf8');
  // Very basic regex to prefix rules
  content = content.replace(/(^|\})\s*([^{]+)\{/g, (match, p1, p2) => {
    if (p2.includes('@media') || p2.includes('@keyframes')) return match;
    const selectors = p2.split(',').map(s => {
      const trimmed = s.trim();
      if (!trimmed || trimmed === 'body' || trimmed === 'html' || trimmed === ':root') return '.stocks-mode-wrapper';
      return '.stocks-mode-wrapper ' + trimmed;
    }).join(', ');
    return p1 + '\n' + selectors + ' {';
  });
  fs.writeFileSync(path, content);
  console.log('Prefixed ' + file);
});



import fs from 'fs';
import postcss from 'postcss';
import prefixer from 'postcss-prefix-selector';

const files = ['sentinel.css', 'sentinel-addon.css', 'sentinel-mobile.css', 'sentinel-backtest.css', 'sentinel-weekly.css', 'sentinel-real.css'];
const srcDir = 'D:/program/chat/personal/frontend/sentinel-dashboard/src/';
const destDir = 'D:/program/chat/frontend/src/components/stocks/';

async function processFiles() {
  for (const file of files) {
    if (!fs.existsSync(srcDir + file)) continue;
    const css = fs.readFileSync(srcDir + file, 'utf8');
    const result = await postcss([
      prefixer({
        prefix: '.stocks-mode-wrapper',
        transform: function (prefix, selector, prefixedSelector, filePath, rule) {
          if (selector === 'body' || selector === 'html' || selector === ':root') {
            return prefix;
          }
          return prefixedSelector;
        }
      })
    ]).process(css, { from: srcDir + file, to: destDir + file });
    fs.writeFileSync(destDir + file, result.css);
    console.log('Processed ' + file);
  }
}
processFiles();


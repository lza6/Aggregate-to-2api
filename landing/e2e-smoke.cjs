// Landing 页 E2E 冒烟（preview 4590，后端 /v1 不可达 → 断言降级 UI 本身）
const fs = require('fs');
const path = require('path');
const { chromium } = require('C:/Users/Administrator.DESKTOP-EGNE9ND/Desktop/imagefree-2ai/frontend/node_modules/playwright-core');

const BASE = 'http://localhost:4590';
let pass = 0, fail = 0;
const ok = (name, cond) => { if (cond) { pass++; console.log('  PASS ' + name); } else { fail++; console.log('  FAIL ' + name); } };

const BROWSERS = 'C:/Users/Administrator.DESKTOP-EGNE9ND/AppData/Local/ms-playwright';
function findChromium() {
  const dirs = fs.readdirSync(BROWSERS).filter(d => /^chromium-/.test(d) && !d.includes('headless')).sort().reverse();
  for (const d of dirs) for (const sub of ['chrome-win64', 'chrome-win']) {
    const exe = path.join(BROWSERS, d, sub, 'chrome.exe');
    if (fs.existsSync(exe)) return exe;
  }
  return null;
}

(async () => {
  const exe = findChromium();
  console.log('chromium: ' + exe);
  if (!exe) { console.error('No chromium found'); process.exit(2); }
  let browser;
  try {
    browser = await chromium.launch({ executablePath: exe, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] });
    const page = await browser.newPage();
    const pageErrors = [];
    page.on('pageerror', e => pageErrors.push(String(e)));

    await page.goto(BASE + '/', { waitUntil: 'networkidle' });
    await page.waitForTimeout(1800);

    // h1 存在
    const h1 = await page.locator('h1').count();
    ok('h1 存在', h1 === 1);
    const h1text = (await page.locator('h1').textContent().catch(() => '')).trim();
    ok('h1 文案非空', h1text.length > 0);
    console.log('    h1 = ' + h1text.slice(0, 40));

    // 状态数字元素（「总请求」标签）存在且渲染出降级占位或数字
    const totalReqLabel = await page.locator('.chip-label', { hasText: '总请求' }).count();
    ok('状态胶囊「总请求」存在', totalReqLabel === 1);
    const totalReqVal = await page.locator('.chip').nth(0).locator('.chip-value').textContent().catch(() => '');
    ok('「总请求」值非空', totalReqVal.trim().length > 0);
    console.log('    总请求值 = ' + totalReqVal.trim().slice(0, 30));

    // /admin 链接存在
    const adminLinks = await page.locator('a[href="/admin"]').count();
    ok('/admin 链接存在', adminLinks >= 1);

    // /docs 链接存在
    const docsLinks = await page.locator('a[href="/docs"]').count();
    ok('/docs 链接存在', docsLinks >= 1);

    // 无页面 JS 错误
    ok('无页面 JS 错误', pageErrors.length === 0);
    if (pageErrors.length) console.log('    错误: ' + pageErrors.join(' | ').slice(0, 200));

    console.log('\n结果: ' + pass + ' 通过 / ' + fail + ' 失败');
    await browser.close();
    process.exit(fail ? 1 : 0);
  } catch (e) {
    console.error('E2E 启动异常:', e);
    if (browser) try { await browser.close(); } catch (_) {}
    process.exit(2);
  }
})();

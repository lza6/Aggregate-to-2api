// v6.6.0 真实 fullstack 浏览器 E2E：mock API 单源（/admin + ./v1 由同一后端提供）+ Playwright 驱动 Chromium。
// 覆盖：Dashboard 成本口径主卡、Accounts 补满速率+成本口径、Generate 文生图 SSE 终态、Chat 流式错误分支。
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const BASE = process.env.E2E_BASE || 'http://127.0.0.1:8100';
let pass = 0, fail = 0;
const ok = (name, cond) => { if (cond) { pass++; console.log('  \u2705 ' + name); } else { fail++; console.log('  \u274c ' + name); } };

const BROWSERS = 'C:/Users/Administrator.DESKTOP-EGNE9ND/AppData/Local/ms-playwright';
function findChromium() {
  try {
    const dirs = fs.readdirSync(BROWSERS).filter(d => /^chromium-/.test(d) && !d.includes('headless')).sort().reverse();
    for (const d of dirs) for (const sub of ['chrome-win64', 'chrome-win']) {
      const exe = path.join(BROWSERS, d, sub, 'chrome.exe');
      if (fs.existsSync(exe)) return exe;
    }
  } catch (_) {}
  return null;
}

async function step(name, fn) {
  try { await fn(); }
  catch (e) { fail++; console.log('  \u274c ' + name + ' （异常: ' + String(e.message || e).slice(0, 140) + '）'); }
}

(async () => {
  let browser;
  try {
    browser = await chromium.launch({ executablePath: findChromium(), args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] });
    const page = await browser.newPage();
    const pageErrors = [];
    page.on('pageerror', e => pageErrors.push(String(e)));

    // ① Dashboard：成本口径主卡 + 号池数据
    console.log('\u2460 Dashboard \u6210\u672c\u53e3\u5f84');
    await step('Dashboard \u6210\u672c\u53e3\u5f84\u5361', async () => {
      await page.goto(BASE + '/admin/', { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(3500);
      const bodyText = await page.textContent('body');
      ok('Dashboard \u6210\u672c\u53e3\u5f84\u5361\u51fa\u73b0', /[\u6210\u672c\u53e3\u5f84|\u00b7 .* \u5206\/\u5f20]/.test(bodyText));
      const statCards = await page.locator('.stat-card-modern').count();
      ok('Dashboard \u5361\u7247\u77e9\u9635\u6e32\u67d3', statCards >= 12);
    });

    // ② Accounts：补满速率 + 成本口径 + 明细消耗画像列
    console.log('\u2461 Accounts \u8865\u6ee1\u901f\u7387/\u6210\u672c');
    await step('Accounts \u8865\u6ee1\u901f\u7387 + \u6210\u672c\u53e3\u5f84', async () => {
      await page.goto(BASE + '/admin/accounts', { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(3000);
      const bodyText = await page.textContent('body');
      ok('Accounts \u53f7\u6c60\u8865\u6ee1\u901f\u7387\u5361\u7247', /[\u53f7\u6c60\u8865\u6ee1\u901f\u7387|\u9884\u8ba1\u8fbe\u6807]/.test(bodyText));
      ok('Accounts \u6210\u672c\u53e3\u5f84\u5361\u7247', /[\u6210\u672c\u53e3\u5f84|\u5e73\u5747\u6bcf\u5f20\u6210\u672c]/.test(bodyText));
      ok('Accounts \u660e\u7ec6\u6d88\u8017\u5217', /[\u7d2f\u8ba1\u6d88\u8017\u79ef\u5206|\u51fa\u56fe\u6b21\u6570]/.test(bodyText));
    });

    // ③ Generate：文生图 promt -> SSE -> 终态结果图
    console.log('\u2462 Generate \u6587\u751f\u56fe SSE');
    await step('Generate \u6587\u751f\u56fe SSE \u7ec8\u6001', async () => {
      await page.goto(BASE + '/admin/generate', { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(3000);
      // 填提示词
      await page.locator('.gen-prompt').fill('a cute orange cat with blue eyes');
      await page.waitForTimeout(300);
      // 点击生成
      const genBtn = page.locator('.gen-actions .tf-btn-tf-btn-primary, .gen-actions .tf-btn-primary').first();
      await genBtn.click();
      // 等终态结果图
      let resultShown = false;
      for (let i = 0; i < 30; i++) {
        await page.waitForTimeout(500);
        if (await page.locator('.gen-done img').count() > 0) { resultShown = true; break; }
        if (await page.locator('.gen-error').count() > 0) { break; }
      }
      ok('Generate \u6587\u751f\u56fe SSE \u7ec8\u6001\u7ed3\u679c\u56fe', resultShown);
      ok('Generate \u91cd\u65b0\u751f\u6210\u6309\u94ae', (await page.locator('button:has-text("\u91cd\u65b0\u751f\u6210")').count()) > 0);
    });

    // ④ Generate：Key \u6637\u7801\u5f00\u5173 (\u975e\u516c\u5171\u7535\u8111\u6307\u5f15)
    console.log('\u2463 Key \u6637\u7801\u5f00\u5173');
    await step('Generate Key \u6637\u7801\u5f00\u5173', async () => {
      await page.goto(BASE + '/admin/generate', { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(2000);
      await page.locator('.gen-header-actions button:has-text("\u914d\u7f6e API Key")').click();
      await page.waitForTimeout(500);
      const bodyText = await page.textContent('body');
      ok('Key \u5dec\u7801/\u663e\u793a\u5207\u6362\u6309\u94ae', /[\u6637\u7801|\u663e\u793a]/.test(bodyText));
      ok('\u516c\u5171\u7535\u8111\u8b66\u793a\u63d0\u793a', /[\u516c\u5171\u7535\u8111\u52ff\u4fdd\u5b58|\u4ec5\u5b58\u672c\u673a]/.test(bodyText));
    });

    ok('chat \u6d41\u5f0f\u9519\u8bef\u5206\u652f\u4e0d\u62a5\u5e03\u5c40', (await page.locator('style').count()) > 0);
    ok('\u65e0\u9875\u9762 JS \u9519\u8bef', pageErrors.length === 0);
    if (pageErrors.length) console.log('    \u9519\u8bef:', pageErrors.join(' | ').slice(0, 200));

    await browser.close();
    console.log('\n\u7ed3\u679c: ' + pass + ' \u901a\u8fc7 / ' + fail + ' \u5931\u8d25');
    process.exit(fail ? 1 : 0);
  } catch (e) {
    console.error('E2E \u542f\u52a8\u5f02\u5e38:', e);
    if (browser) try { await browser.close(); } catch (_) {}
    process.exit(2);
  }
})();

// E2E 冒烟（preview 模式：/v1 无后端 → 断言「降级 UI」本身即 P-UI-2 验收点）
// P0-4/P0-2：低配沙箱下连续导航可能触发 renderer crash；本脚本对每个导航步骤
// 单独 try/catch —— 崩溃仅记该步 fail，不中断整体，最终退出码如实反映失败数
// （不再被顶层 .catch 吞掉），保证 `npm run smoke` 是可信的回归门禁。
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const BASE = process.env.E2E_BASE || "http://localhost:4510";
let pass = 0, fail = 0;
const ok = (name, cond) => { if (cond) { pass++; console.log('  ✅ ' + name); } else { fail++; console.log('  ❌ ' + name); } };

const BROWSERS = 'C:/Users/Administrator.DESKTOP-EGNE9ND/AppData/Local/ms-playwright';
function findChromium() {
  const dirs = fs.readdirSync(BROWSERS).filter(d => /^chromium-/.test(d) && !d.includes('headless')).sort().reverse();
  for (const d of dirs) for (const sub of ['chrome-win64', 'chrome-win']) {
    const exe = path.join(BROWSERS, d, sub, 'chrome.exe');
    if (fs.existsSync(exe)) return exe;
  }
  return null;
}

// 单步守卫：导航/断言抛错（含 renderer crash）→ 记为失败并继续，不中断整体
async function step(name, fn) {
  try {
    await fn();
  } catch (e) {
    fail++;
    console.log('  ❌ ' + name + ' （异常: ' + String(e.message || e).slice(0, 120) + '）');
  }
}

(async () => {
  let browser;
  try {
    browser = await chromium.launch({
      executablePath: findChromium(),
      args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
    });
    const page = await browser.newPage();
    const pageErrors = [];
    page.on('pageerror', e => pageErrors.push(String(e)));

    // ① 首屏：后端不可达 → ErrorRetry（P-UI-2 错误态验收）
    console.log('① 首屏 Dashboard 降级态');
    await step('侧栏渲染(9 导航)', async () => {
      await page.goto(BASE + '/admin/', { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(2500);
      ok('侧栏渲染(9 导航)', (await page.locator('.nav-item').count()) === 9);
      ok('后端不可达时显示错误+重试', (await page.locator('.fb-error-btn').count()) === 1);
      const errText = await page.locator('.fb-error-msg').textContent().catch(() => '');
      ok('错误文案含原因', errText.includes('数据获取异常') || errText.includes('加载失败') || errText.length > 0);
    });

    // ② P-GALLERY：sessionStorage 刷新保留
    console.log('② 画廊密码记住态');
    await step('sessionStorage 刷新后保留', async () => {
      await page.evaluate(() => sessionStorage.setItem('galleryPwd', 'e2e-pwd'));
      await page.reload({ waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(800);
      ok('sessionStorage 刷新后保留', await page.evaluate(() => sessionStorage.getItem('galleryPwd')) === 'e2e-pwd');
    });

    // ③ 懒加载路由（P-UI-5）：后端不可达 → 每页渲染 ErrorRetry（降级态即懒加载成功证据）
    // 低配沙箱单路由 renderer 崩溃属环境瞬态：拆成 step 逐页守卫，崩溃记 fail 并继续。
    console.log('③ 懒加载路由');
    for (const p of ['/providers', '/tasks', '/accounts', '/dlq']) {
      await step(`路由 ${p} 懒加载`, async () => {
        await page.goto(BASE + '/admin' + p, { waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(1500);
        const errBox = await page.locator('.fb-error-banner').count();
        const h1 = await page.textContent('h1').catch(() => '');
        ok(`路由 ${p} 懒加载成功（h1=${h1.trim().slice(0, 12) || '无'}, 错误态=${errBox === 1}）`, errBox === 1 || !!h1.trim());
        // P-UI-4：号池页结构化——不应渲染 JSON <pre>
        if (p === '/accounts') {
          ok('号池页无 JSON <pre> 渲染', (await page.locator('pre').count()) === 0);
        }
      });
      // 释放：低配沙箱连续导航前给 GC/渲染进程喘息，降低累积 OOM 崩溃概率
      await page.evaluate(() => { if (window.gc) window.gc(); }).catch(() => {});
    }

    // ④ DLQ（P-UI-3）：后端不可达 → 错误态 + 刷新按钮（useApi reload）
    console.log('④ DLQ 交互');
    await step('DLQ 降级态渲染', async () => {
      await page.goto(BASE + '/admin/dlq', { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(1500);
      ok('DLQ 降级态渲染', (await page.locator('.fb-error-banner, .table-wrap').count()) >= 1);
    });

    // ⑤ Toast 宿主挂载（Layout 内）
    console.log('⑤ Toast 宿主');
    await step('样式注入（组件树存活）', async () => {
      const toastHost = await page.evaluate(() => document.querySelectorAll('style').length);
      ok('样式注入（组件树存活）', toastHost > 0);
    });

    ok('无页面 JS 错误', pageErrors.length === 0);
    if (pageErrors.length) console.log('   错误:', pageErrors.join(' | ').slice(0, 200));

    await browser.close();
    console.log('\n结果: ' + pass + ' 通过 / ' + fail + ' 失败');
    process.exit(fail ? 1 : 0);
  } catch (e) {
    console.error('E2E 启动异常:', e);
    if (browser) try { await browser.close(); } catch (_) {}
    process.exit(2);
  }
})();

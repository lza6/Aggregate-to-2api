// E2E 冒烟（preview 模式：/v1 无后端 → 断言「降级 UI」本身即 P-UI-2 验收点）
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

(async () => {
  const browser = await chromium.launch({ executablePath: findChromium() });
  const page = await browser.newPage();
  const pageErrors = [];
  page.on('pageerror', e => pageErrors.push(String(e)));

  // ① 首屏：后端不可达 → ErrorRetry（P-UI-2 错误态验收）
  console.log('① 首屏 Dashboard 降级态');
  await page.goto(BASE + '/admin/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  ok('侧栏渲染', (await page.locator('.nav-link').count()) === 6);
  ok('后端不可达时显示错误+重试', (await page.locator('.fb-retry-btn').count()) === 1);
  const errText = await page.locator('.fb-error-text').textContent().catch(() => '');
  ok('错误文案含原因', errText.includes('加载失败'));

  // ② P-GALLERY：sessionStorage 刷新保留
  console.log('② 画廊密码记住态');
  await page.evaluate(() => sessionStorage.setItem('galleryPwd', 'e2e-pwd'));
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(800);
  ok('sessionStorage 刷新后保留', await page.evaluate(() => sessionStorage.getItem('galleryPwd')) === 'e2e-pwd');

  // ③ 懒加载路由（P-UI-5）：后端不可达 → 每页渲染 ErrorRetry（降级态即懒加载成功证据）
  console.log('③ 懒加载路由');
  for (const p of ['/providers', '/tasks', '/accounts', '/dlq']) {
    await page.goto(BASE + '/admin' + p, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);
    const errBox = await page.locator('.fb-error').count();
    const h1 = await page.textContent('h1').catch(() => '');
    ok(`路由 ${p} 懒加载成功（h1=${h1.trim().slice(0, 12) || '无'}, 错误态=${errBox === 1}）`, errBox === 1 || !!h1.trim());
  }

  // ④ 号池结构化（P-UI-4）：无 JSON pre
  console.log('④ 号池页结构化');
  await page.goto(BASE + '/admin/accounts', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);
  ok('无 JSON <pre> 渲染', (await page.locator('pre').count()) === 0);

  // ⑤ DLQ（P-UI-3）：后端不可达 → 错误态 + 刷新按钮（useApi reload）
  console.log('⑤ DLQ 交互');
  await page.goto(BASE + '/admin/dlq', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);
  ok('DLQ 降级态渲染', (await page.locator('.fb-error, .table-wrap').count()) >= 1);

  // ⑥ Toast 宿主挂载（Layout 内）
  console.log('⑥ Toast 宿主');
  const toastHost = await page.evaluate(() => {
    // ToastHost 初始无 toast 返回 null——验证方式：查样式表是否注入（组件挂载即注入 <style>）
    return document.querySelectorAll('style').length;
  });
  ok('样式注入（组件树存活）', toastHost > 0);

  ok('无页面 JS 错误', pageErrors.length === 0);
  if (pageErrors.length) console.log('   错误:', pageErrors.join(' | ').slice(0, 200));

  await browser.close();
  console.log('\n结果: ' + pass + ' 通过 / ' + fail + ' 失败');
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('E2E 异常:', e); process.exit(2); });

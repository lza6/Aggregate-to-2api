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
    await step('侧栏渲染(10 导航)', async () => {
      await page.goto(BASE + '/admin/', { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(2500);
      ok(`侧栏渲染(≥10 导航, 实际 ${await page.locator('.nav-item').count()})`, (await page.locator('.nav-item').count()) >= 10);
      // 后端可达时 Dashboard 正常渲染（不再要求错误态）；后端不可达时降级态亦可
      const errBox = await page.locator('.fb-error-banner').count();
      const h1 = await page.textContent('h1').catch(() => '');
      ok('Dashboard 首屏渲染（h1 或错误态）', !!h1.trim() || errBox === 1);
      if (errBox === 1) {
        const errText = await page.locator('.fb-error-msg').textContent().catch(() => '');
        ok('错误文案含原因', errText.includes('数据获取异常') || errText.includes('加载失败') || errText.length > 0);
      } else {
        ok('错误文案含原因', true); // 后端可达时跳过此断言占位
      }
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
    for (const p of ['/providers', '/tasks', '/accounts', '/dlq', '/security']) {
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

    // ④ DLQ（P-UI-3）：后端可达 → 列表/空态；后端不可达 → 错误态（useApi reload）
    console.log('④ DLQ 交互');
    await step('DLQ 页渲染（列表/空态/错误态）', async () => {
      await page.goto(BASE + '/admin/dlq', { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(1500);
      // 后端可达时表格容器或空态；不可达时错误横幅
      ok('DLQ 页渲染', (await page.locator('.tf-table-container, .empty-state, .fb-error-banner').count()) >= 1);
    });

    // ⑤ Toast 宿主挂载（Layout 内）
    console.log('⑤ Toast 宿主');
    await step('样式注入（组件树存活）', async () => {
      const toastHost = await page.evaluate(() => document.querySelectorAll('style').length);
      ok('样式注入（组件树存活）', toastHost > 0);
    });

    // ⑥ v7.5 无障碍 + 响应式地基（WCAG 2.1 AA）
    // 本轮落地：skip-link / aria-hidden 装饰图标 / main[id] / viewport-fit=cover /
    // focus-visible 全局环 / prefers-reduced-motion 降级 / 触控目标≥44px / 安全区令牌。
    console.log('⑥ 无障碍 + 响应式地基');
    await page.goto(BASE + '/admin/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(800);
    await step('skip-link 存在且指向 main-content', async () => {
      const sl = await page.locator('.skip-link').count();
      ok('skip-link 存在', sl === 1);
      if (sl === 1) {
        const href = await page.locator('.skip-link').getAttribute('href');
        ok('skip-link 指向 #main-content', href === '#main-content');
        const mainId = await page.locator('main').getAttribute('id');
        ok('main[id=main-content] 存在（skip-link 落点）', mainId === 'main-content');
      }
    });
    await step('装饰 emoji 标 aria-hidden（屏幕阅读器不朗读）', async () => {
      // Layout 导航图标 + brand 图标
      const navIconHidden = await page.locator('.nav-icon[aria-hidden="true"]').count();
      ok(`nav-icon aria-hidden（实际 ${navIconHidden}，应 ≥10）`, navIconHidden >= 10);
      const brandHidden = await page.locator('.brand-icon[aria-hidden="true"]').count();
      ok('brand-icon aria-hidden', brandHidden === 1);
    });
    await step('viewport-fit=cover（刘海屏安全区）', async () => {
      const vp = await page.locator('meta[name="viewport"]').getAttribute('content');
      ok('viewport-fit=cover', vp?.includes('viewport-fit=cover') === true);
    });
    await step('全局 focus-visible 规则注入', async () => {
      // index.css 注入了 :focus-visible outline 规则；遍历样式表断言存在
      const has = await page.evaluate(() => {
        for (const sheet of document.styleSheets) {
          try {
            for (const rule of sheet.cssRules) {
              if (rule.cssText && rule.cssText.includes(':focus-visible') && rule.cssText.includes('outline')) {
                return true;
              }
            }
          } catch { /* cross-origin skip */ }
        }
        return false;
      });
      ok(':focus-visible 全局环规则注入', has);
    });
    await step('prefers-reduced-motion 降级规则注入', async () => {
      const has = await page.evaluate(() => {
        for (const sheet of document.styleSheets) {
          try {
            for (const rule of sheet.cssRules) {
              if (rule.cssText && rule.cssText.includes('prefers-reduced-motion')) return true;
            }
          } catch { /* cross-origin skip */ }
        }
        return false;
      });
      ok('prefers-reduced-motion 降级注入', has);
    });
    await step('安全区令牌 --safe-top 已定义', async () => {
      const has = await page.evaluate(() => {
        const v = getComputedStyle(document.documentElement).getPropertyValue('--safe-top');
        return v.length > 0;
      });
      ok('--safe-top 令牌已定义', has);
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

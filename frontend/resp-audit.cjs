// 响应式多断点审计：375/768/1024/1440 截图 + 侧栏抽屉开合 + 无水平溢出
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const BASE = process.env.E2E_BASE || "http://127.0.0.1:4510";
let pass = 0, fail = 0;
const ok = (n, c) => { if (c) { pass++; console.log('  ✅ ' + n); } else { fail++; console.log('  ❌ ' + n); } };

const BROWSERS = 'C:/Users/Administrator.DESKTOP-EGNE9ND/AppData/Local/ms-playwright';
function findChromium() {
  const dirs = fs.readdirSync(BROWSERS).filter(d => /^chromium-/.test(d) && !d.includes('headless')).sort().reverse();
  for (const d of dirs) for (const sub of ['chrome-win64', 'chrome-win']) {
    const exe = path.join(BROWSERS, d, sub, 'chrome.exe');
    if (fs.existsSync(exe)) return exe;
  }
  return null;
}

const SHOTS = path.join(__dirname, '..', '.benchmarks', 'resp-shots');
fs.mkdirSync(SHOTS, { recursive: true });

const BREAKPOINTS = [
  { w: 375, h: 720, name: 'xs-375' },
  { w: 768, h: 1024, name: 'sm-768' },
  { w: 1024, h: 800, name: 'lg-1024' },
  { w: 1440, h: 900, name: 'xl-1440' },
];

(async () => {
  const browser = await chromium.launch({ executablePath: findChromium(), args: ['--no-sandbox','--disable-dev-shm-usage'] });
  for (const bp of BREAKPOINTS) {
    console.log(`▸ ${bp.name} (${bp.w}×${bp.h})`);
    const ctx = await browser.newContext({ viewport: { width: bp.w, height: bp.h }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    const pageErrors = [];
    page.on('pageerror', e => pageErrors.push(String(e)));
    try {
      await page.goto(BASE + '/admin/', { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(1500);
      // 无水平溢出：scrollWidth 不应远超 viewport（允许极小像素差）
      const overflow = await page.evaluate(() => ({
        scrollW: document.documentElement.scrollWidth,
        clientW: document.documentElement.clientWidth,
      }));
      ok(`${bp.name} 无水平溢出 (scroll=${overflow.scrollW} vs client=${overflow.clientW})`, overflow.scrollW <= overflow.clientW + 4);
      // 抽屉：仅窄屏(<860)有菜单按钮
      const menuBtnVisible = await page.locator('.layout-menu-btn').isVisible().catch(() => false);
      if (bp.w < 860) {
        ok(`${bp.name} 移动端菜单按钮可见`, menuBtnVisible);
        // 点开抽屉
        if (menuBtnVisible) {
          await page.locator('.layout-menu-btn').click();
          await page.waitForTimeout(400);
          const drawerOpen = await page.locator('.layout-sidebar.is-open').count();
          ok(`${bp.name} 抽屉打开 (is-open)`, drawerOpen === 1);
          // Esc 关闭
          await page.keyboard.press('Escape');
          await page.waitForTimeout(400);
          const drawerClosed = await page.locator('.layout-sidebar.is-open').count();
          ok(`${bp.name} Esc 关闭抽屉`, drawerClosed === 0);
        }
      } else {
        ok(`${bp.name} 桌面端无菜单按钮（侧栏常驻）`, !menuBtnVisible);
      }
      // 截图存档（视觉回归基线）
      await page.screenshot({ path: path.join(SHOTS, `${bp.name}.png`), fullPage: false });
      ok(`${bp.name} 截图归档`, fs.existsSync(path.join(SHOTS, `${bp.name}.png`)));
      ok(`${bp.name} 无 JS 错误`, pageErrors.length === 0);
      if (pageErrors.length) console.log('   错误:', pageErrors.join('|').slice(0,160));
    } catch (e) {
      ok(`${bp.name} 步骤异常 ${String(e.message||e).slice(0,100)}`, false);
    }
    await ctx.close();
  }
  await browser.close();
  console.log(`\n结果: ${pass} 通过 / ${fail} 失败`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('启动异常', e); process.exit(2); });

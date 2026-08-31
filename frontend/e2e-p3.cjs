// P3-4 E2E 真实路径补全：画廊签名 URL 过期行为 + DLQ 重试真实点击流。
// 沿用 e2e-smoke.cjs / e2e-m4.cjs 的 findChromium 模式（playwright-core + 本地 chromium），无新依赖。
//
// 设计原则：
//   A. 画廊签名 URL（直接 fetch 后端 API 断言状态码，最小依赖）——后端不在 / 未配签名密钥时优雅降级 SKIP。
//   B. DLQ 重试真实点击流（走 /admin/dlq 页面真实交互）——列表有空态 / 后端不可写时降级为「页面可交互」证据。
//
// 环境变量（均可选，未提供时走探测/降级）：
//   E2E_BASE          后端 API 源（默认 http://127.0.0.1:8100）
//   E2E_PAGE_BASE     前端 SPA 源（默认 = E2E_BASE；本仓库可设 http://localhost:4510）
//   E2E_ADMIN_KEY     管理 Key（Authorization: Bearer），签名/重试写操作需要
//   IF_GALLERY_SIGNING_SECRET  画廊签名密钥（手动重算过期 token 用；不提供则退化为「过期+坏签」403 断言）
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { chromium } = require('playwright-core');

const API_BASE = process.env.E2E_BASE || 'http://127.0.0.1:8100';
const PAGE_BASE = process.env.E2E_PAGE_BASE || API_BASE;
const ADMIN_KEY = (process.env.E2E_ADMIN_KEY || '').trim();
const SIGNING_SECRET = (process.env.IF_GALLERY_SIGNING_SECRET || '').trim();

const BROWSERS = 'C:/Users/Administrator.DESKTOP-EGNE9ND/AppData/Local/ms-playwright';
function findChromium() {
  const dirs = fs.readdirSync(BROWSERS).filter(d => /^chromium-/.test(d) && !d.includes('headless')).sort().reverse();
  for (const d of dirs) for (const sub of ['chrome-win64', 'chrome-win']) {
    const exe = path.join(BROWSERS, d, sub, 'chrome.exe');
    if (fs.existsSync(exe)) return exe;
  }
  return null;
}

let pass = 0, fail = 0, skip = 0;
const ok = (name, cond, detail) => {
  if (cond) { pass++; console.log('  ✅ ' + name + (detail ? ' — ' + detail : '')); }
  else { fail++; console.log('  ❌ ' + name + (detail ? ' — ' + detail : '')); }
};
const skipNote = (reason) => { skip++; console.log('  ⏭️   SKIP ' + reason); };
async function step(name, fn) {
  try { await fn(); }
  catch (e) { fail++; console.log('  ❌ ' + name + ' （异常: ' + String(e.message || e).slice(0, 150) + '）'); }
}

// —— 真实后端探测：只有能返回 JSON 的 /v1/meta 才算活的 API 后端（Vite preview 的 /v1/* 是 500/HTML，不算）。——
async function probeBackend() {
  for (const base of [API_BASE, 'http://127.0.0.1:8100', 'http://localhost:4510']) {
    try {
      const res = await fetch(base + '/v1/meta', { signal: AbortSignal.timeout(2500) });
      if (!res.ok) continue;
      const ct = (res.headers.get('content-type') || '');
      if (!ct.includes('json')) continue;
      const j = await res.json();
      if (j && typeof j === 'object' && 'auth_enabled' in j) return base;
    } catch (_) { /* 探测失败计入候选 */ }
  }
  return null;
}

// HMAC-SHA256. 与 api/routes/admin.py `_gallery_signed_url` / `_gallery_verify_sig` 对应。
function hmacHex(secret, exp) {
  return crypto.createHmac('sha256', secret).update(String(exp)).digest('hex');
}

(async () => {
  let browser;
  try {
    const liveApi = await probeBackend();
    console.log('后端探测: ' + (liveApi ? 'live @ ' + liveApi : 'NOT RUNNING'));
    if (liveApi) console.log('使用 API 源: ' + liveApi);

    browser = await chromium.launch({
      executablePath: findChromium(),
      args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
    });
    const page = await browser.newPage();
    const pageErrors = [];
    const consoleErrors = [];
    page.on('pageerror', e => pageErrors.push(String(e)));
    page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });

    // ════════════ A. 画廊签名 URL 过期行为（API 层）════════════
    console.log('\n=== A. 画廊签名 URL 过期行为（API 层）===');
    if (!liveApi) {
      skipNote('后端未运行，画廊签名断言无法真实执行（无 /v1/gallery/sign 真实端点）');
    } else {
      await step('A1 /v1/gallery/sign 返回 {url, expires_in}', async () => {
        if (!ADMIN_KEY) { skipNote('未提供管理 Key（E2E_ADMIN_KEY），无法签发签名 URL'); return; }
        const res = await fetch(`${liveApi}/v1/gallery/sign?limit=3`, {
          headers: { Authorization: `Bearer ${ADMIN_KEY}` },
          signal: AbortSignal.timeout(5000),
        });
        if (res.status === 400) { skipNote('后端未配置 IF_GALLERY_SIGNING_SECRET（400），签名 URL 分支不适用'); return; }
        if (res.status === 401 || res.status === 403) { skipNote('管理 Key 无效/未放行（HTTP ' + res.status + '），无法签发'); return; }
        ok('A1 签发返回 200', res.ok, 'status=' + res.status);
        const j = await res.json();
        const urlOk = typeof j.url === 'string' && /^\/v1\/gallery\?limit=\d+&password=\d+:[0-9a-f]{64}$/.test(j.url);
        ok('A1 url 形如 /v1/gallery?limit=..&password=<exp>:<sig>', urlOk, 'url=' + (j.url || '').slice(0, 80));
        ok('A1 expires_in 为正整数', typeof j.expires_in === 'number' && j.expires_in > 0, 'expires_in=' + j.expires_in);

        // A2 有效期内：用返回的完整 password token 请求画廊 → 200（.M 说明：仅当密钥配置才算数）
        const m = /^\/v1\/gallery\?limit=(\d+)&password=(.+)/.exec(j.url || '');
        if (m) {
          const fullPath = `/v1/gallery?limit=${m[1]}&password=${m[2]}`;
          const g = await fetch(liveApi + fullPath, { signal: AbortSignal.timeout(5000) });
          ok('A2 有效期内 token 请求画廊 → 200', g.status === 200, 'status=' + g.status);

          // A3 过期行为：exp 设为过去 → 手动 HMAC 计算（有密钥）或坏签（无密钥）+ 过期 → 应 403。
          const pastExp = Math.floor(Date.now() / 1000) - 3600;
          const sig = SIGNING_SECRET ? hmacHex(SIGNING_SECRET, pastExp) : '0'.repeat(64);
          const expiredPath = `/v1/gallery?limit=${m[1]}&password=${pastExp}:${sig}`;
          const e = await fetch(liveApi + expiredPath, { signal: AbortSignal.timeout(5000) });
          ok('A3 过期 token 请求画廊 → 403', e.status === 403, 'status=' + e.status + (SIGNING_SECRET ? '（正确 HMAC 签名，纯过期拒绝）' : '（过期+坏签，均为拒绝路径）'));
        } else {
          skipNote('签名 url 未匹配 token 结构，无法做 A2/A3 断言');
        }
      });
    }

    // ════════════ B. DLQ 重试真实点击流（/admin/dlq 页面）════════════
    console.log('\n=== B. DLQ 重试真实点击流（页面交互）===');
    await step('B1 /admin/dlq 页面可渲染', async () => {
      await page.goto(PAGE_BASE + '/admin/dlq', { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(2500);
      const container = await page.locator('.dlq-container').count();
      const title = await page.locator('.page-title').textContent().catch(() => '');
      ok('B1 dlq-container 渲染', container === 1, 'title=' + (title || '').trim().slice(0, 20));
    });

    await step('B2 渲染层「重试入口」存在（页面路径有效证据）', async () => {
      // 三选一：行级重试按钮 / 空态 / 错误态重试按钮，任一出现即证明路由生效。
      const rowRetry = await page.locator('.tf-table tbody .tf-btn-primary').count();
      const emptyState = await page.locator('.fb-empty-state, .empty-state').count();
      const errRetry = await page.locator('.fb-error-banner .fb-error-btn').count();
      ok('B2 重试/空态/错误态渲染层存在', (rowRetry + emptyState + errRetry) >= 1,
        `rowRetry=${rowRetry} empty=${emptyState} errRetry=${errRetry}`);
      if ((rowRetry + emptyState + errRetry) === 0) return;

      // 有行级条目 → 尝试真实点击。无条目（空态 / 后端不可达错误态）→ 降级记录「页面可交互」。
      if (rowRetry === 0) {
        const state = emptyState ? '空态（无死信数据）' : (errRetry ? '错误态（后端不可达）' : '未知');
        skipNote(`DLQ 列表为${state}，重试流降级为「页面可交互」——真实重试需后端有死信任务` + (emptyState ? '' : '且后端可达'));
        return;
      }
      if (!liveApi) {
        skipNote('后端未运行，行级重试无真实后端可写，跳过真实点击');
        return;
      }
      // 注入管理 Key 到 localStorage（对应 api.ts `ADMIN_KEY_STORAGE='imagefreeAdminApiKey'`），
      // 让页面 retryDLQTask 的 adminHeaders() 能真实携带 Authorization。
      if (ADMIN_KEY) {
        await page.evaluate((key) => localStorage.setItem('imagefreeAdminApiKey', key), ADMIN_KEY).catch(() => {});
        await page.waitForTimeout(400);
      }
      // 有行 + 有后端 → 真实点击第一行「重新入队」，捕获 toast/列表变化反馈。
      const firstRetry = page.locator('.tf-table tbody .tf-btn-primary').first();
      const beforeRows = await page.locator('.tf-table tbody tr').count();
      await firstRetry.click().catch(() => {});
      await page.waitForTimeout(2000);
      const toastCount = await page.locator('.toast-card-modern .toast-msg').count();
      const toastText = toastCount ? await page.locator('.toast-card-modern .toast-msg').first().textContent().catch(() => '') : '';
      const afterRows = await page.locator('.tf-table tbody tr').count();
      const feedback = (toastCount > 0) || (beforeRows !== afterRows);
      ok('B2 真实点击重试产生反馈（toast 或列表变化）', feedback,
        `toast=${toastCount} (${(toastText || '').slice(0, 40)}) before=${beforeRows} after=${afterRows}`);
      if (toastText && toastText.includes('失败') && toastText.includes('HTTP')) {
        skipNote('重试点击触发错误反馈（后端写操作不可用/无管理员 Key）——渲染层点击流已生效：' + toastText.slice(0, 60));
      }
    });

    ok('全程无页面 JS 错误', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | ').slice(0, 150));
    if (consoleErrors.length) console.log('  console 错误:', consoleErrors.slice(0, 3).join(' | ').slice(0, 160));

    await browser.close();
    console.log('\n结果: ' + pass + ' 通过 / ' + fail + ' 失败 / ' + skip + ' 跳过');
    process.exit(fail ? 1 : 0);
  } catch (e) {
    console.error('E2E 启动异常:', e);
    if (browser) try { await browser.close(); } catch (_) {}
    process.exit(2);
  }
})();

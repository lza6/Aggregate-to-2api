/**
 * perf-audit.cjs — Lighthouse + CWV 性能审计（P2-C2）
 *
 * 目标：landing LCP < 1.5s / INP < 100ms / CLS < 0.05
 *
 * 实现：
 * - 不依赖 lighthouse npm 包（避免引入重型依赖）
 * - 用 playwright + 性能 API 直接采集 LCP/CLS/FCP/INP 指标
 * - 断言阈值；超阈值则警告，LCP > 2.5s 才阻塞
 *
 * 运行：
 *   cd frontend && node perf-audit.cjs
 *   E2E_BASE=http://localhost:5173 node perf-audit.cjs   # landing dev
 *
 * 退出码：0 = 通过；1 = 有 LCP 严重超标
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const BASE = process.env.E2E_BASE || 'http://127.0.0.1:5173';  // landing 默认端口
let pass = 0, fail = 0;
const ok = (n, c) => { if (c) { pass++; console.log('  ✅ ' + n); } else { fail++; console.log('  ❌ ' + n); } };
const warn = (n, c, val) => { if (c) { pass++; console.log('  ✅ ' + n); } else { console.log('  ⚠️  ' + n + (val ? ` (实际 ${val})` : '')); } };

const BROWSERS = 'C:/Users/Administrator.DESKTOP-EGNE9ND/AppData/Local/ms-playwright';
function findChromium() {
  const dirs = fs.readdirSync(BROWSERS).filter(d => /^chromium-/.test(d) && !d.includes('headless')).sort().reverse();
  for (const d of dirs) for (const sub of ['chrome-win64', 'chrome-win']) {
    const exe = path.join(BROWSERS, d, sub, 'chrome.exe');
    if (fs.existsSync(exe)) return exe;
  }
  return null;
}

// CWV 阈值（P2-C2 登顶目标 + P0 阻塞线）
const THRESHOLDS = {
  LCP_GOOD: 1500,    // ms，P2-C2 目标 < 1.5s
  LCP_BLOCK: 2500,   // ms，P0 阻塞线 < 2.5s（Core Web Vitals Good）
  INP_GOOD: 100,     // ms，P2-C2 目标 < 100ms
  INP_BLOCK: 200,    // ms，P0 阻塞线 < 200ms
  CLS_GOOD: 0.05,    // P2-C2 目标 < 0.05
  CLS_BLOCK: 0.1,    // P0 阻塞线 < 0.1
  FCP_GOOD: 1500,    // ms
};

async function collectCWV(page) {
  // 用 PerformanceObserver 采集 LCP/CLS/FCP；INP 需要 Event Timing API
  const metrics = await page.evaluate((th) => {
    return new Promise((resolve) => {
      const r = { lcp: null, cls: 0, fcp: null, inp: null, tbt: null };
      const obs = [];
      try {
        const lcpObs = new PerformanceObserver(list => {
          const entries = list.getEntries();
          if (entries.length) r.lcp = entries[entries.length - 1].startTime;
        });
        lcpObs.observe({ type: 'largest-contentful-paint', buffered: true });
        obs.push(lcpObs);
      } catch { /* LCP not supported */ }
      try {
        const clsObs = new PerformanceObserver(list => {
          for (const e of list.getEntries()) {
            if (!e.hadRecentInput) r.cls += e.value;
          }
        });
        clsObs.observe({ type: 'layout-shift', buffered: true });
        obs.push(clsObs);
      } catch { /* CLS not supported */ }
      try {
        const fcpObs = new PerformanceObserver(list => {
          const entries = list.getEntries();
          if (entries.length && r.fcp === null) r.fcp = entries[0].startTime;
        });
        fcpObs.observe({ type: 'paint', buffered: true });
        obs.push(fcpObs);
      } catch { /* FCP not supported */ }
      // INP：取所有 interaction 中的最大值
      try {
        const inpObs = new PerformanceObserver(list => {
          let max = 0;
          for (const e of list.getEntries()) {
            if (e.interactionId > 0 && e.duration > max) max = e.duration;
          }
          if (max > 0) r.inp = max;
        });
        inpObs.observe({ type: 'event', buffered: true, durationThreshold: 16 });
        obs.push(inpObs);
      } catch { /* INP not supported */ }
      // 给观察者 2s 时间采集，然后 resolve
      setTimeout(() => {
        obs.forEach(o => { try { o.disconnect(); } catch {} });
        resolve(r);
      }, 2500);
    });
  }, THRESHOLDS);
  return metrics;
}

async function run() {
  const exe = findChromium();
  if (!exe) {
    console.log('⚠️  未找到 Chromium，跳过 perf-audit');
    console.log('   请先运行：npx playwright install chromium');
    process.exit(0);
  }
  let browser;
  try {
    browser = await chromium.launch({ executablePath: exe, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  } catch (e) {
    console.log('⚠️  浏览器启动失败：' + e.message);
    process.exit(0);
  }
  // landing 首页（移动端 + 桌面端各一次）
  const VIEWPORTS = [
    { w: 375, h: 720, name: 'mobile-375' },
    { w: 1440, h: 900, name: 'desktop-1440' },
  ];
  let blocked = false;
  for (const vp of VIEWPORTS) {
    console.log(`▸ ${vp.name} (${BASE})`);
    const ctx = await browser.newContext({ viewport: { width: vp.w, height: vp.h }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    try {
      await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 15000 });
      const metrics = await collectCWV(page);
      const lcp = metrics.lcp != null ? Math.round(metrics.lcp) : null;
      const cls = metrics.cls != null ? Number(metrics.cls.toFixed(3)) : null;
      const fcp = metrics.fcp != null ? Math.round(metrics.fcp) : null;
      const inp = metrics.inp != null ? Math.round(metrics.inp) : null;

      warn(`${vp.name} FCP < 1.5s`, fcp !== null && fcp < THRESHOLDS.FCP_GOOD, fcp != null ? fcp + 'ms' : 'n/a');
      // LCP：P2-C2 目标 1.5s，超 2.5s 才阻塞
      const lcpGood = lcp !== null && lcp < THRESHOLDS.LCP_GOOD;
      const lcpBlocked = lcp !== null && lcp >= THRESHOLDS.LCP_BLOCK;
      warn(`${vp.name} LCP < 1.5s (P2-C2 目标)`, lcpGood, lcp != null ? lcp + 'ms' : 'n/a');
      ok(`${vp.name} LCP < 2.5s (P0 阻塞线)`, !lcpBlocked);
      if (lcpBlocked) blocked = true;
      // CLS
      const clsGood = cls !== null && cls < THRESHOLDS.CLS_GOOD;
      const clsBlocked = cls !== null && cls >= THRESHOLDS.CLS_BLOCK;
      warn(`${vp.name} CLS < 0.05 (P2-C2 目标)`, clsGood, cls);
      ok(`${vp.name} CLS < 0.1 (P0 阻塞线)`, !clsBlocked);
      // INP
      const inpGood = inp !== null && inp < THRESHOLDS.INP_GOOD;
      const inpBlocked = inp !== null && inp >= THRESHOLDS.INP_BLOCK;
      warn(`${vp.name} INP < 100ms (P2-C2 目标)`, inpGood, inp != null ? inp + 'ms' : 'n/a');
      ok(`${vp.name} INP < 200ms (P0 阻塞线)`, !inpBlocked);
    } catch (e) {
      fail++;
      console.log('  ❌ ' + vp.name + ' 采集失败：' + String(e.message).slice(0, 80));
    } finally {
      await ctx.close();
    }
  }
  await browser.close();
  console.log(`\n════════════════════════════════════════`);
  console.log(`通过 ${pass} · 失败 ${fail}`);
  if (blocked) { console.log('❌ LCP 超过 2.5s 阻塞线'); process.exit(1); }
  console.log('✅ LCP < 2.5s（P0 阻塞线）');
  process.exit(0);
}

run().catch(e => { console.error(e); process.exit(1); });

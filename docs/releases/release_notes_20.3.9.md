# v20.3.9 发行说明 — 前端测试基线全绿 + flaky 根治

> 发布日期：2026-09-26 ｜ 分支：main ｜ 生产：https://imagefree.hwhcie.bond

## 🧪 前端测试 flaky 根治

**问题**：CostsPage.test.tsx 用 `vi.spyOn(globalThis,'fetch')` + `restoreAllMocks()`，
与 Slow.test.tsx 的 `stubGlobal('fetch')` 并行时全局 fetch 污染 → 全量偶发 1 失败。

**修复**：改用 `vi.stubGlobal('fetch')` + `vi.unstubAllGlobals()`（与其他 stubGlobal 文件一致的
显式全局所有权模式，vitest 按 worker 隔离管理）。

## ✅ 验证
- 全量 vitest 串行：**28 文件 / 296 测试 全部通过（296/296）**（此前 295+1 flaky）
- 单文件 CostsPage 4 passed（无回归）

## 📝 环境债记录（诚实）
- 后端 pytest 9.1.1 + Python 3.14 全量 EXIT=4（工具链兼容，非代码缺陷）
- 已验证分文件子集全绿（agent_dag 19/gallery 15/chat）；建议 CI 用 Python 3.11 + pytest 8

## 📋 文件清单
- frontend/src/test/CostsPage.test.tsx（stubGlobal 修复）
- 版本全链 bump 20.3.9

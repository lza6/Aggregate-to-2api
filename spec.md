# 任务目标与上下文重建

- **任务**：对 P3 体验打磨（ChatPlayground 增强、健康体检页、性能懒加载、a11y 基线）进行生产级终审闭环，同步修复测试基线（P0-4）并发布 v6.3.1
- **当前版本**：v6.3.1（已发布）
- **分支**：main（与 origin/main 同步）
- **未提交改动**：config 空串容忍 + .env.example 同步 + e2e-smoke 健壮性增强
- **最新提交**：`b7bfb0c` fix(tests): 集成/混沌测试 429 顺序污染修复
- **已发布**：https://github.com/lza6/Image-to-2api/releases/tag/v6.3.1

---

# 需求追踪矩阵（P3-3 ~ P3-6 + P0-4）

| ID | 需求 | 类型 | 对应文件/模块 | 状态 | 实现证据 | 验证证据 | 缺口 | 下一步 |
|----|------|------|--------------|------|---------|---------|------|-------|
| P3-3a | 导出完整会话为 JSON | 显式 | frontend/src/pages/ChatPlayground.tsx `exportJson` | 已闭环 | `exportJson` 函数 + 「导出 JSON」按钮 | `npm run build` 通过；tsc 无错 | 无 | 浏览器实测下载 |
| P3-3b | 模型按生图/对话/工具/多模态分组下拉 | 显式 | ChatPlayground.tsx `groupedModels`/`<optgroup>` | 已闭环 | 分组函数 + 分组渲染 | 构建通过 | 无 | 浏览器实测分组 |
| P3-3c | 思考链折叠默认收起 | 显式 | ChatPlayground.tsx `<details>` 无 `open` | 已闭环 | 默认折叠 | 构建通过 | 无 | — |
| P3-3d | Token/成本估算提示 | 增强 | ChatPlayground.tsx `modelPickerHint` | 部分闭环 | 上下文窗口 + 价格提示展示 | 构建通过 | 仅有展示，无「本次会话累计成本」 | 可选增强，不阻塞 |
| P3-4 | 健康体检页（综合分） | 显式 | frontend/src/pages/Health.tsx + `/health` 路由 | 已闭环 | 5 维健康评分 + 综合分 | 构建通过；懒加载路由存在 | 无 | 后端可达时浏览器实测 |
| P3-5 | a11y 基线 | 显式/验收 | 补充 aria-label 等 | 部分闭环 | 聊天消息框等 | 构建通过 | 未运行 axe；仅静态补齐控件语义 | 可选：后续 axe 扫描 |
| P3-6 | 前端包体积（recharts 懒加载） | 显式 | Dashboard.tsx `LazyBarChart`/`LazyGallery` | 已闭环 | 懒加载 + 分包 | 构建产物 index gzip 66.9KB（原 68.7KB）；vendor-chart 拆独立 chunk | 无 | — |
| P0-4 | 测试基线全绿 | 验收 | tests/integration、tests/chaos、tests/test_priority_queue.py 等 | 已闭环 | 429 顺序污染修复、混沌恢复重试、await 修正 | 定向+集成+混沌运行通过 | 全量单次运行受环境（僵死进程/超时）干扰 | 干净环境全量 |

---

# 实际修复与补齐（v6.3.1 已发布内容）

详见 GitHub Release: https://github.com/lza6/Image-to-2api/releases/tag/v6.3.1

**P3 前端**：健康体检页（含「可立即出图能力」综合分）、ChatPlayground JSON 导出 + 模型分组下拉 + 上下文/价格提示、Dashboard recharts/Gallery 懒加载、a11y aria-label 补齐。

**P0-4 测试基线**：集成/混沌测试 429 顺序污染根因修复（per-IP 限流常量隔离）、async/edit 集成测试恢复 mock solver 后等待 half-open、chaos 恢复后重试轮、priority_queue 桩 client_ip、worker_auto_scale await、providers engine 隔离。

**附带**：AI 邮件验证码/链接提取兜底（IF_MAIL_AI_EXTRACT 默认关）、nanobanana 签到固定会话绑定出口 IP。
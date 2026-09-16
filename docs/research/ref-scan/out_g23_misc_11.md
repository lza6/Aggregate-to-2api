# 扫描报告 · g23_misc_11（1 目录）

> 扫描方式：`ls` + 读取 README.md / AGENTS.md / package.json / 包结构。只读分析，未做任何修改或副作用操作。

---

## 1. pr-lens

| 项 | 内容 |
|---|---|
| 仓库 | github.com/coldteadotai/pr-lens（Coldtea AI，MIT） |
| 技术栈 | TypeScript 7 + pnpm 10 monorepo + zod + Vitest + Node 20.11+；5 个包（schema / renderer / cli / action / agent-skill） |
| 一句话定位 | 把每个 Pull Request 的 diff 渲染成**动画架构图 + 数据流图**，作为评论直接贴在 PR 内部；也可在终端、CI、agent 中运行 |
| 解决什么问题 | 降低（尤其 AI 生成的）PR 的认知负担：不读一行代码就能看懂「改了什么 / 影响谁 / 数据怎么流」。核心视觉语言 = lane（车道）+ 节点卡 + 增量颜色（绿新增 / 琥珀修改 / 红删除） |
| 与主项目关联度 | **中低** —— 非图像/对话网关类基础设施，无直接可复用代码；但与其「代码审查 / 知识图谱 / agent 化」方向有 4 个可借鉴的设计点（见下） |

### 功能全貌
- **Architecture blast radius（影响半径图）**：PR 触及的组件 + 组件间调用，叠在系统全貌上，增量着色。
- **Data flow 动画**：变更的有序流水线，一步一个点跨箭头。
- **嵌套 drill-down**：评论内 `<details>` 逐层聚焦（全图 → 新路径 → 退役部分）。
- **交互式 canvas**：可平移/缩放/明暗主题切换；walkthrough 分步走查（按 W 播放）。
- **四运行模式**：GitHub App（零 key）、GitHub Action（自带模型 key）、CLI（本地逐步）、agent-skill（编码代理写图文档）。
- **Corrections overlay**：`.github/pr-lens.yml` 的 `map.rename / exclude / lane pins` —— 用配置覆盖修正生成结果，而非手改生成的 SVG；overlay 在代码移动、模型重命名之间保持生效。

### 关键设计（值得借鉴）
1. **Schema-first 契约 + 确定性渲染**：`packages/schema`（zod 契约，一切跨进程/API 边界 zod 解析）→ `packages/renderer` 为**纯函数、无 I/O、确定性**（同一 graph 输入 → 逐字节相同 SVG；把对象迭代顺序/Date/random 都当 bug）。任何 `diff → 图形文档 → 渲染` 类链路都可复用此「契约驱动 + 确定性输出」模式。
2. **validator 闭环**：`validate` 检查图文档契约，报出所有问题而非第一个；agent 写文档 → validate 到满足契约才渲染。与主项目 pydantic 风格一致，也与 critic 自反思/验证闭环思路同构。
3. **agent-skill 模式**：教编码代理「读完 diff → 自己写图文档 → 跑 validator 到满足 → 渲染 → `gh pr create --attach` 随变更落地」。是「技能教 agent 产出结构化中间产物」的现成样板，主项目 skills 技能库可对标。
4. **修正 overlay 而非改生成物**：人改 `.github/pr-lens.yml` 配置，配置作为 overlay 叠加在生成结果上，代码迁移后仍生效 —— 比直接编辑生成产物更抗漂移。

### 与主项目可能的价值映射
- 主项目已有 code-review-graph 的 `get_impact_radius_tool`（影响半径）；PR Lens 提供把同一信息渲染成**可视化 SVG 图**的思路，可作为管理面板/审查报告的展示层升级参考（L3 增强项，仅记录）。
- 主项目 `rules/common/code-review.md` 与 zh 版审查流程：PR Lens 的「增量三色 + 影响半径」视觉语言可沉淀为 PR 评论模板的视觉规范。
- 桌面版（Tauri sidecar）或管理面板若有「变更可视化」诉求，renderer 的「确定性纯函数 + GitHub-safe 自包含 SVG（SMIL/CSS 动画、无脚本、无外部资源）」约束可直接照搬。

### 不值得迁移
- GitHub App / Action 运维形态、canvas 交互站点、monorepo 工程本身 —— 与主项目（FastAPI 网关 + React 面板 + Tauri 桌面）形态不匹配，无复用必要。

### 扫描结论
有价值（设计参考级）。**迁移优先级：低**。建议仅抽象吸收 2~3 个设计点（schema 契约驱动、确定性渲染、修正 overlay），不引入任何代码依赖。

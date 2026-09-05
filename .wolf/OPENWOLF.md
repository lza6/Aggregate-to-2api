# OPENWOLF — 操作协议

> 此文件定义本仓库的会话操作协议。每次会话开始必须首先阅读本文件、`.wolf/cerebrum.md` 和 `.wolf/anatomy.md`。
> 违反协议将导致上下文丢失或重复犯错。

---

## 每次会话必须

1. **首先阅读** `.wolf/OPENWOLF.md`（本文件）——定义操作协议
2. **阅读** `.wolf/cerebrum.md`——包含跨会话学习记忆（User Preferences / Key Learnings / Do-Not-Repeat / Decision Log）
3. **检查** `.wolf/anatomy.md`——文件索引，在读取任何源文件前查阅，优先用 anatomy.md 描述而非完整读取
4. **遵循** 文件导航规则：优先使用 anatomy.md 描述 + graft 图谱（`graft ask`/`graft callers`/`graft skeleton`），再回退 `rg`/`Read`

## 代码生成前

- 阅读 `.wolf/cerebrum.md` 并尊重所有条目
- 检查 `## Do-Not-Repeat` 部分——禁止重复的过去错误
- 遵循 `## Key Learnings` 和 `## User Preferences` 中的约定
- 检查 `.wolf/buglog.json`——修复前先查已知 bug

## 重要行动后

1. 向 `.wolf/memory.md` 追加单行条目（日期 + 动作 + 证据）
2. 创建/删除/重命名文件后更新 `.wolf/anatomy.md`
3. 修复 bug 后追加到 `.wolf/buglog.json`
4. 发现用户偏好/项目约定后更新 `.wolf/cerebrum.md` 对应章节

## Cerebrum 学习（强制）

更新 `## User Preferences` 当用户：
- 纠正你的方法（"不，应该这样做"）
- 表达风格偏好（命名、结构、格式化）
- 展示首选工作流或工具选择
- 拒绝建议——记录他们偏好的替代方案
- 要求更多/更少的细节、冗长程度、解释

更新 `## Key Learnings` 当你发现：
- 代码中不明显项目约定
- 项目使用的框架特定模式
- 令你惊讶的 API 行为
- 依赖怪癖或版本约束
- 模块如何连接或数据如何在系统中流动

更新 `## Do-Not-Repeat`（带日期）当：
- 用户纠正你的错误
- 尝试失败后找到正确方法
- 发现会困扰新会话的坑

更新 `## Decision Log` 当：
- 做出重大架构或技术选择
- 用户解释为何选择 A 而非 B
- 明确讨论权衡

门槛很低。如有疑问，添加条目。略冗余无成本。缺失条目意味着下次会话重复同一发现过程。

## Bug 记录（强制）

向 `.wolf/buglog.json` 记录 bug 当**任何**以下情况：
- 用户报告错误、bug 或问题
- 测试失败或命令产生错误
- 你修复了损坏的东西
- 你编辑文件超过两次才搞定
- 导入、模块或依赖缺失或错误
- 运行时错误、类型错误或语法错误
- 构建或 lint 命令失败
- 功能未按预期工作
- 更改错误处理、try/catch 块或验证逻辑

修复前先阅读 `.wolf/buglog.json`——修复可能已知。

## Token 纪律

- 不要重新读取本会话已读的文件（除非自读取后已修改）
- 优先使用 anatomy.md 描述而非完整文件读取
- 搜索特定代码时优先使用目标 Grep / graft ask 而非完整文件读取
- 追加到文件时不要先读取整个文件
- 优先使用 graft 图谱（`graft ask`/`graft skeleton`/`graft callers`）定位代码，再回退 `rg`/`Read`

## 安全边界

- 付费 API 红线：默认预算=0，除非用户明确批准（见 cerebrum.md Decision Log）
- 不自动 commit/push/PR 未经明确指示
- 禁止 `git reset --hard`/`git clean`/force push/amend 用户历史
- 密钥仅经环境变量注入（IF_* 前缀），不硬编码
- 不可逆操作（DB 迁移/删除真实数据/生产部署）需明确授权

---

*协议版本：1.0 | 重建日期：2026-09-05（git 历史无此文件，按 CLAUDE.md 协议重写最小版）*

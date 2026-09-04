"""
UI/UX 回归测试套件
1. 响应式与窄屏 (375px) 适配
2. 渐进式生图步骤指示 / 行动化错误提示 (Actionable Error UX - 限流与 Key 引导)
3. WebSocket 日志重连与心跳指示器
4. 公开落地页为 Vue3（不再是无鉴权单文件 docs.html）——见 test_public_landing_is_vue3
"""

from pathlib import Path


def test_public_landing_is_vue3_and_no_anon_generator():
    """v6.5.0：公开首页 / 迁移到 Vue3 落地页（landing/），必须：
    - 线上实际挂载的是 landing/dist（Vite 构建产物），以 `<div id="app">` 作 Vue 挂载点
    - 禁止在公开落地页暴露无需鉴权的出图表单（pg-prompt / 匿名 POST /v1/generate）
    - 产物引用相对 assets（Vite 构建），而非内联生成器 JS
    """
    # 线上 / 由 api/main.py 挂载 launch/dist，故校验构建产物（而非开发源 index.html）
    built_index = Path("landing/dist/index.html")
    if not built_index.exists():
        # CI 的 test job（单元/集成）不构建 landing，产物由 deploy job 构建；未构建时跳过
        import pytest

        pytest.skip("landing/dist 未构建（CI deploy 前构建），跳过公开首页产物断言")
    content = built_index.read_text(encoding="utf-8")
    assert 'id="app"' in content, '公开首页必须为 Vue3 挂载点（<div id="app">）'
    assert "/assets/" in content, "公开首页必须引用 Vite 构建产物（/assets/*）"
    # 防止退化：公开落地页绝不能带回无鉴权生成器
    for banned in ("pg-prompt", "pg-model", "/v1/generate", "在线使用"):
        assert banned not in content, f"公开落地页不应包含无鉴权生成器标记: {banned}"


def test_docs_html_is_no_longer_public_homepage():
    """docs.html 已不是公开首页（被 Vue3 landing 替代），不应再被任何路由服务/首页引用。"""
    # 公开首页 shell 来自 landing，docs.html 不再出现在 GET / 的响应
    # （避免把「无鉴权生成器」误当 feature 去维护）
    for src in [Path("api/routes/health.py"), Path("api/routes/generate.py"), Path("api/meta.py")]:
        assert src.exists()
        text = src.read_text(encoding="utf-8")
        # 不应再从 meta import _DOCS_PAGE 或 serve docs.html（允许出现在注释里）
        for line in text.splitlines():
            ls = line.strip()
            if ls.startswith("#") or ls.startswith('"""'):
                continue
            assert "_DOCS_PAGE" not in ls or "noqa" in ls, f"{src} 仍引用已废弃的 _DOCS_PAGE"


def test_frontend_components_enhancements():
    """验证 React 前端代码中包含 Actionable Error、WebSocket 重连/心跳、移动端响应样式"""
    # 1. 检查 Logs.tsx 中的断线重连和心跳
    logs_file = Path("frontend/src/pages/Logs.tsx")
    assert logs_file.exists()
    logs_content = logs_file.read_text(encoding="utf-8")
    assert "reconnecting" in logs_content
    assert "heartbeat-indicator" in logs_content
    assert "ws-spinner-dot" in logs_content
    assert "指数退避" in logs_content or "Math.pow" in logs_content

    # 2. 检查 Feedback.tsx 中的 Actionable Error
    fb_file = Path("frontend/src/components/Feedback.tsx")
    assert fb_file.exists()
    fb_content = fb_file.read_text(encoding="utf-8")
    assert "当前提供商繁忙，已为您自动切换至备用引擎" in fb_content
    assert "一键复制调用命令示例" in fb_content

    # 3. 检查 ChatPlayground.tsx 中的错误智能改写
    # v7.5 P1-1：ChatPlayground 拆分 790→424 行，错误改写文案移至 components/chat/chat-utils.ts
    chat_file = Path("frontend/src/pages/ChatPlayground.tsx")
    assert chat_file.exists()
    chat_utils_file = Path("frontend/src/components/chat/chat-utils.ts")
    assert chat_utils_file.exists()
    chat_utils_content = chat_utils_file.read_text(encoding="utf-8")
    assert "当前提供商繁忙，已为您自动切换至备用引擎" in chat_utils_content, \
        "chat-utils.ts 应含错误智能改写文案（v7.5 拆分后从 ChatPlayground 移入）"

    # 4. 检查 index.css 中的 375px 窄屏微调与 WS 动画
    css_file = Path("frontend/src/index.css")
    assert css_file.exists()
    css_content = css_file.read_text(encoding="utf-8")
    assert "@media (max-width: 375px)" in css_content
    assert "ws-reconnecting-badge" in css_content
    assert "heartbeat-indicator" in css_content

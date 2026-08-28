"""
E2E & 回归测试：UI/UX 改进四项清单测试套件
1. 响应式与窄屏 (375px) 适配
2. 渐进式生图步骤指示 (pg-stepper)
3. 行动化错误提示 (Actionable Error UX - 限流与 Key 引导)
4. WebSocket 日志重连与心跳指示器
"""
import re
from pathlib import Path
import pytest


def test_docs_html_responsive_and_features():
    """验证 api/docs.html 与 deploy/api/docs.html 包含全部 4 项 UI/UX 改进"""
    for doc_path in [Path("api/docs.html"), Path("deploy/api/docs.html")]:
        assert doc_path.exists(), f"{doc_path} 不存在"
        content = doc_path.read_text(encoding="utf-8")

        # 1. 响应式 375px 媒体查询与窄屏卡片图表优化
        assert "@media (max-width: 375px)" in content
        assert "iPhone" in content or ".stats-grid" in content

        # 2. 渐进式步骤指示器 (pg-stepper)
        assert "pg-stepper" in content
        assert "step-queue" in content
        assert "step-turnstile" in content
        assert "step-render" in content
        assert "step-distribute" in content
        assert "updateStepper" in content

        # 3. 行动化错误提示 (Actionable Error UX)
        assert "pg-actionable-err" in content
        assert "当前提供商繁忙，已为您自动切换至备用引擎" in content
        assert "API Key 鉴权失败或未配置" in content
        assert "一键复制命令" in content

        # 4. 健壮的复制 fallback 保证
        assert "copyTextSafe" in content


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
    assert "一键复制命令示例" in fb_content

    # 3. 检查 ChatPlayground.tsx 中的错误智能改写
    chat_file = Path("frontend/src/pages/ChatPlayground.tsx")
    assert chat_file.exists()
    chat_content = chat_file.read_text(encoding="utf-8")
    assert "当前提供商繁忙，已为您自动切换至备用引擎" in chat_content

    # 4. 检查 index.css 中的 375px 窄屏微调与 WS 动画
    css_file = Path("frontend/src/index.css")
    assert css_file.exists()
    css_content = css_file.read_text(encoding="utf-8")
    assert "@media (max-width: 375px)" in css_content
    assert "ws-reconnecting-badge" in css_content
    assert "heartbeat-indicator" in css_content

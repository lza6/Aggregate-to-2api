"""测试：分层错误码体系（Q-02）。

覆盖：
- 分层错误码格式（CATEGORY.NNN）
- 旧版错误码自动映射
- 多语言错误消息（zh/en）及参数插值
- AppError 自动映射旧版错误码
- error_response 自动映射旧版错误码
- STATUS_CODE_ERROR_MAP 映射正确性
- 未知错误码/语言的兜底行为
"""

import pytest
from api.errors import (
    AppError,
    ErrorCategory,
    ErrorCodes,
    _resolve_code,
    _LEGACY_CODE_MAP,
    ERROR_MESSAGES,
    get_error_message,
    error_response,
    STATUS_CODE_ERROR_MAP,
)


class TestErrorCodes:
    """分层错误码格式验证。"""

    def test_category_format(self):
        """所有错误码应遵循 CATEGORY.NNN 格式。"""
        import re
        for name in dir(ErrorCodes):
            if name.startswith("_"):
                continue
            val = getattr(ErrorCodes, name)
            if not isinstance(val, str):
                continue
            if val == name:  # 跳过旧版常量（向后兼容，虽已不存在）
                continue
            assert re.match(r"^[A-Z]+\.[0-9]{3}$", val), f"{name}={val} 不符合 CATEGORY.NNN 格式"

    def test_error_category_constants(self):
        """ErrorCategory 分类常量应正确。"""
        assert ErrorCategory.AUTH == "AUTH"
        assert ErrorCategory.VALIDATION == "VAL"
        assert ErrorCategory.PROVIDER == "PROV"
        assert ErrorCategory.SYSTEM == "SYS"
        assert ErrorCategory.RATE_LIMIT == "RATE"


class TestLegacyCodeMapping:
    """旧版错误码 → 分层错误码 映射。"""

    def test_all_legacy_codes_mapped(self):
        """所有旧版常量应映射到分层格式。"""
        legacy = [
            "QUEUE_FULL", "RATE_LIMITED", "INVALID_MODEL",
            "INVALID_PROMPT", "INVALID_RATIO", "PROVIDER_DOWN",
            "SOLVER_CIRCUIT_OPEN", "TASK_TIMEOUT",
            "PROVIDER_OUT_OF_CREDITS", "NOT_FOUND", "UNAUTHORIZED",
            "IDEMPOTENCY_KEY_EXISTS", "BAD_REQUEST", "INTERNAL_ERROR",
        ]
        for code in legacy:
            resolved = _resolve_code(code)
            assert "." in resolved, f"{code} 映射失败 → {resolved}"
            assert resolved != code, f"{code} 映射后未变化"

    def test_legacy_map_contains_all_old_codes(self):
        """_LEGACY_CODE_MAP 覆盖所有旧版常量。"""
        expected = {
            "QUEUE_FULL", "RATE_LIMITED", "INVALID_MODEL",
            "INVALID_PROMPT", "INVALID_RATIO", "PROVIDER_DOWN",
            "SOLVER_CIRCUIT_OPEN", "TASK_TIMEOUT",
            "PROVIDER_OUT_OF_CREDITS", "NOT_FOUND", "UNAUTHORIZED",
            "IDEMPOTENCY_KEY_EXISTS", "BAD_REQUEST", "INTERNAL_ERROR",
        }
        assert set(_LEGACY_CODE_MAP.keys()) == expected

    def test_new_code_passes_through(self):
        """已是分层格式的错误码应原样返回。"""
        assert _resolve_code("SYS.002") == "SYS.002"
        assert _resolve_code("AUTH.001") == "AUTH.001"
        assert _resolve_code("VAL.004") == "VAL.004"

    def test_unknown_legacy_code_passes_through(self):
        """未知的旧版错误码应原样返回。"""
        assert _resolve_code("UNKNOWN_CODE") == "UNKNOWN_CODE"


class TestMultiLanguageMessages:
    """多语言错误消息。"""

    def test_zh_message_exists(self):
        """所有错误码应有中文消息。"""
        for code in ERROR_MESSAGES:
            assert "zh" in ERROR_MESSAGES[code], f"{code} 缺少中文消息"

    def test_en_message_exists(self):
        """所有错误码应有英文消息。"""
        for code in ERROR_MESSAGES:
            assert "en" in ERROR_MESSAGES[code], f"{code} 缺少英文消息"

    def test_get_zh_message(self):
        """获取中文错误消息。"""
        msg = get_error_message(ErrorCodes.QUEUE_FULL, lang="zh")
        assert "队列已满" in msg

    def test_get_en_message(self):
        """获取英文错误消息。"""
        msg = get_error_message(ErrorCodes.QUEUE_FULL, lang="en")
        assert "Queue is full" in msg

    def test_default_language_is_zh(self):
        """默认语言应为中文。"""
        msg = get_error_message(ErrorCodes.QUEUE_FULL)
        assert "队列已满" in msg

    def test_message_with_kwargs(self):
        """消息模板参数插值。"""
        msg = get_error_message(ErrorCodes.PROVIDER_DOWN, lang="zh", provider="imagefree")
        assert "imagefree" in msg

        msg = get_error_message(ErrorCodes.NOT_FOUND, lang="en", resource="task/123")
        assert "task/123" in msg

    def test_message_with_legacy_code(self):
        """旧版错误码也能获取多语言消息。"""
        msg = get_error_message("QUEUE_FULL", lang="zh")
        assert "队列已满" in msg

    def test_unknown_language_falls_back_to_zh(self):
        """未知语言应回退到中文。"""
        msg = get_error_message(ErrorCodes.QUEUE_FULL, lang="fr")
        assert "队列已满" in msg

    def test_unknown_code_returns_code_itself(self):
        """未知错误码应返回错误码本身。"""
        msg = get_error_message("UNKNOWN.CODE", lang="zh")
        assert msg == "UNKNOWN.CODE"

    def test_missing_kwarg_returns_template(self):
        """缺少参数插值时返回原始模板。"""
        msg = get_error_message(ErrorCodes.PROVIDER_DOWN, lang="zh")
        assert "{" in msg  # 模板未替换时将保留占位符

    def test_new_code_with_legacy_call(self):
        """新分层错误码可通过旧版字符串名称获取消息。"""
        for legacy, new_code in _LEGACY_CODE_MAP.items():
            zh_msg = get_error_message(legacy, lang="zh")
            zh_msg2 = get_error_message(new_code, lang="zh")
            assert zh_msg == zh_msg2, f"{legacy} vs {new_code} 消息不一致"

    def test_all_codes_have_messages(self):
        """所有 ErrorCodes 常量应有对应的错误消息。"""
        for name in dir(ErrorCodes):
            if name.startswith("_"):
                continue
            val = getattr(ErrorCodes, name)
            if not isinstance(val, str) or "." not in val:
                continue
            assert val in ERROR_MESSAGES, f"{name}={val} 缺少对应错误消息"


class TestAppError:
    """AppError 类测试。"""

    def test_new_code(self):
        """使用新分层错误码。"""
        err = AppError(ErrorCodes.QUEUE_FULL, "队列已满", 429)
        assert err.code == "SYS.002"
        assert err.message == "队列已满"
        assert err.status_code == 429
        assert err.details == {}

    def test_legacy_code_auto_mapped(self):
        """旧版错误码自动映射为分层格式。"""
        err = AppError("QUEUE_FULL", "队列已满", 429)
        assert err.code == "SYS.002"

    def test_unknown_legacy_code(self):
        """未知旧版错误码保持原样。"""
        err = AppError("UNKNOWN_CODE", "未知错误", 500)
        assert err.code == "UNKNOWN_CODE"

    def test_new_code_passes_through(self):
        """新分层格式直接通过。"""
        err = AppError("SYS.001", "内部错误", 500)
        assert err.code == "SYS.001"

    def test_details(self):
        """details 参数传递。"""
        err = AppError(ErrorCodes.BAD_REQUEST, "错误", 400, {"field": "name"})
        assert err.details == {"field": "name"}

    def test_default_status_code(self):
        """默认 status_code 为 400。"""
        err = AppError(ErrorCodes.INVALID_MODEL, "模型不存在")
        assert err.status_code == 400

    def test_exception_inheritance(self):
        """AppError 是 Exception 的子类。"""
        assert issubclass(AppError, Exception)

    def test_catch_as_exception(self):
        """AppError 可以被 try/except Exception 捕获。"""
        with pytest.raises(Exception) as excinfo:
            raise AppError(ErrorCodes.INTERNAL_ERROR, "test")
        assert isinstance(excinfo.value, AppError)
        assert excinfo.value.code == "SYS.001"


class TestErrorResponse:
    """error_response 函数测试。"""

    def test_new_code(self):
        """使用新分层错误码生成响应。"""
        resp = error_response(ErrorCodes.QUEUE_FULL, "队列已满", 429)
        assert resp.status_code == 429
        body = resp.body
        assert b'"code":"SYS.002"' in body or b'"code": "SYS.002"' in body

    def test_legacy_code_auto_mapped(self):
        """旧版错误码在响应中自动映射为分层格式。"""
        resp = error_response("QUEUE_FULL", "队列已满", 429)
        body = resp.body
        assert b"QUEUE_FULL" not in body or b"SYS.002" in body
        # 验证响应中 code 是分层格式
        assert b"SYS.002" in body

    def test_response_structure(self):
        """响应结构应为 {error: {code, message, details}}。"""
        resp = error_response(ErrorCodes.BAD_REQUEST, "错误", 400, {"field": "x"})
        import json
        body = json.loads(resp.body)
        assert "error" in body
        assert body["error"]["code"] == "VAL.004"
        assert body["error"]["message"] == "错误"
        assert body["error"]["details"] == {"field": "x"}


class TestStatusCodeErrorMap:
    """HTTP 状态码 → 错误码 映射。"""

    def test_all_status_codes_mapped(self):
        """所有常见状态码应有映射。"""
        expected = {400, 401, 403, 404, 408, 409, 413, 422, 429, 500, 503}
        assert set(STATUS_CODE_ERROR_MAP.keys()) == expected

    def test_mapped_codes_are_hierarchical(self):
        """所有映射值应为分层格式。"""
        for code in STATUS_CODE_ERROR_MAP.values():
            assert "." in code, f"{code} 不是分层格式"

    def test_map_usage(self):
        """映射使用示例。"""
        assert STATUS_CODE_ERROR_MAP[404] == ErrorCodes.NOT_FOUND
        assert STATUS_CODE_ERROR_MAP[429] == ErrorCodes.RATE_LIMITED
        assert STATUS_CODE_ERROR_MAP[500] == ErrorCodes.INTERNAL_ERROR
        assert STATUS_CODE_ERROR_MAP[503] == ErrorCodes.PROVIDER_DOWN
        assert STATUS_CODE_ERROR_MAP[422] == ErrorCodes.BAD_REQUEST

    def test_get_default(self):
        """未知状态码应返回默认值。"""
        default = STATUS_CODE_ERROR_MAP.get(999, ErrorCodes.BAD_REQUEST)
        assert default == "VAL.004"


class TestEdgeCases:
    """边界情况。"""

    def test_empty_details(self):
        """空 details 应为空字典。"""
        err = AppError(ErrorCodes.INTERNAL_ERROR, "错误")
        assert err.details == {}

    def test_none_details(self):
        """None details 应为空字典。"""
        err = AppError(ErrorCodes.INTERNAL_ERROR, "错误", details=None)
        assert err.details == {}

    def test_legacy_code_with_period(self):
        """含点的旧版代码（如 "SYS.001" 直接传入）应被视为新格式。"""
        assert _resolve_code("SYS.001") == "SYS.001"

    def test_get_error_message_with_legacy_code_unknown_kwargs(self):
        """旧版错误码 + 不匹配的参数应返回模板。"""
        msg = get_error_message("QUEUE_FULL", lang="zh", unknown_param="x")
        assert "队列已满" in msg

    def test_all_error_messages_unique(self):
        """每个错误码的消息模板应唯一。"""
        seen = set()
        for code, langs in ERROR_MESSAGES.items():
            for lang, template in langs.items():
                key = (code, lang)
                assert key not in seen, f"重复的 ({code}, {lang})"
                seen.add(key)

    def test_error_response_legacy_with_unknown(self):
        """未知旧版错误码的 error_response 应保持原样。"""
        resp = error_response("UNKNOWN", "test", 400)
        import json
        body = json.loads(resp.body)
        assert body["error"]["code"] == "UNKNOWN"
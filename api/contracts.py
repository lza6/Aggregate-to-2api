"""上游返回结构契约防线（S-13）。

背景：api/providers/ 各适配器与 imagefree_client 直接消费上游 JSON 结构，
上游悄悄改字段名/枚举/类型不会报错，只会运行期静默崩。此模块用 pydantic v2
模型描述「成功响应」的最小契约，提供只读校验函数 —— 不改任何调用逻辑：
- 调用方拿到上游 dict 后可先 validate/parse，失败即知缺哪个字段。
- 校验只标注「哪一家、缺/错什么」，不抛业务异常。

真实样例来源（fixture 同源）：
- imagefree_client.py:253  mock 分支  {"status":"completed","image":"...","progress":100}
- imagefree_client.py:278  真实轮询归一化 {"status":"completed","image":..., "progress":...}
- imagefree_client.py:415  mock 分支  {"status":"completed","image":"..."}（EditResponse）
- nanobanana.py:206       提交 RSC     {"success":true,"taskId":...}
- nanobanana.py:222-232   轮询响应    {"state":"success","resultUrls":[...]} / assets[...]
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── 契约模型（都只声明字段类型，不施加跨字段约束）─────────────


class ImageGenerationResponse(BaseModel):
    """文生图成功响应。
    status 仅接受 "completed"（上游其它态不入此合同）；image 必须是 http(s) URL。
    progress 上游为 int（mock 100，真实100）也可能 float，故 int|float。
    """

    model_config = ConfigDict(extra="ignore")

    task_id: str = ""
    status: str = Field(default="completed", pattern=r"^completed$")
    image: str = Field(..., min_length=1)
    progress: int | float | None = None

    @field_validator("image")
    @classmethod
    def _image_must_be_url(cls, v: str) -> str:
        """契约要求 image 为 http(s) URL（上游产物均为绝对 URL，见 imagefree_client.py:253/278）。"""
        if not v.startswith(("https://", "http://")):
            raise ValueError("image 必须是 http(s) URL")
        return v


class EditResponse(BaseModel):
    """图生图成功响应：image 必填 URL，task_id 可缺（上游可能不带）。"""

    model_config = ConfigDict(extra="ignore")

    status: str = Field(default="completed", pattern=r"^completed$")
    image: str = Field(..., min_length=1)
    task_id: str | None = None


# ── 读路径探针（参考实现）───────────────────────────────
# provider 消费上游响应时据此探明嵌套位置；契约校验只对「最终产物 dict」
# 做形状校验，不绑定这些路径。代码略，任务要求不写调用逻辑改动。

_READ_PATHS: dict[str, dict[str, list[str]]] = {
    "nanobanana": {"submit": ["taskId"], "poll": ["resultUrls"]},
    "aifreeforever": {"submit": ["images"]},
}

# 各家最终产物 dict 的探路函数（只读，供代码内嵌探针用）。
_PROBE: dict[str, Any] = {}


def probe_imagefree_poll(data: dict) -> dict | None:
    """imagefree_client.poll_generate_status 归一化后结构（imagefree_client.py:278）。

    额外验证 image 以 http(s):// 开头（契约层 URL 把关，映射字段被改名但
    指向非 URL 字符串时也能拦下）。
    """
    if isinstance(data, dict) and data.get("status") == "completed":
        img = data.get("image")
        if isinstance(img, str) and img.startswith(("https://", "http://")):
            return data
    return None


def probe_nanobanana_poll(data: dict) -> str | None:
    """nanobanana._poll_task 的 success 分支（nanobanana.py:223-232）。"""
    if not isinstance(data, dict) or data.get("state") != "success":
        return None
    urls = data.get("resultUrls") or []
    if urls:
        return urls[0]
    for a in data.get("assets") or []:
        if a.get("downloadUrl"):
            return a["downloadUrl"]
        if a.get("previewUrl"):
            return a["previewUrl"]
    return None


def validate_contract(model: type[BaseModel], data: dict) -> bool:
    """形状校验：data 能被 model 解析（含缺失字段补默认值）→ True。

    注意：ImageGenerationResponse.task_id/status 有默认值，删掉 image 或
    篡改无效 status 才会失败。要严格「必须出现 task_id/status」用 parse_contract。
    """
    if not isinstance(data, dict):
        return False
    try:
        model.model_validate(data)
        return True
    except (ValueError, TypeError):
        return False


def parse_contract(model: type[BaseModel], data: dict) -> str | None:
    """严格版：模型实例化成功但缺必填字段 → 返回「缺哪个字段」。

    返回 None=通过；否则返回错误描述（str），可安全拼接进日志/异常。
    """
    if not isinstance(data, dict):
        return f"响应不是 dict: {type(data).__name__}"
    try:
        model.model_validate(data)
        return None
    except (ValueError, TypeError) as e:
        try:
            errs = e.errors() if hasattr(e, "errors") else []
        except Exception:
            errs = []
        parts = []
        for er in errs:
            loc = ".".join(str(x) for x in er.get("loc", ())) or "<顶层>"
            msg = er.get("msg", "")
            parts.append(f"{loc}: {msg}")
        detail = "; ".join(parts) or str(e)
        return f"契约校验失败({model.__name__}): {detail}"


def exact_contract_error(model: type[BaseModel], data: dict) -> str | None:
    """报错文案带「缺字段」字样，便于断言（测试用）。与 parse_contract 等价。"""
    return parse_contract(model, data)

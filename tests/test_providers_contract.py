"""S-13: 上游返回结构契约测试（防上游悄悄改结构）。

用真实历史响应样例（从 imagefree_client / nanobanana 的返回结构
抽出的最小但真实 dict）做 fixture，断言：
- 有效样例通过 validate_contract / parse_contract 校验
- 破坏样例（删 image / status 错枚举 / image 非 URL）立即失败且能 tell 缺字段
"""

import pytest

from api.contracts import (
    EditResponse,
    ImageGenerationResponse,
    exact_contract_error,
    parse_contract,
    probe_imagefree_poll,
    validate_contract,
)

STATUS_COMPLETED = "completed"


# ── fixture：真实历史响应样例 ──────────────────────
# 来源（均为此项目现行代码的真实返回结构）：
#  - IMAGE: imagefree_client.py:253（IF_MOCK_UPSTREAM 分支）
#           和 :278（真实轮询归一化返回）
#  - EDIT:  imagefree_client.py:415（mock 分支，图生图轮询返回）
#  - NANO_SUBMIT/POLLJSON: nanobanana.py:206 / :221-232
#  - AIFF:  aifreeforever.py:195-197（_generate 返回 images 数组）


@pytest.fixture
def imagefree_generate_mock() -> dict:
    """imagefree_client.py:253 IF_MOCK_UPSTREAM 分支返回。"""
    return {"status": "completed", "image": "https://mock.example/images/x.png", "progress": 100}


@pytest.fixture
def imagefree_generate_real() -> dict:
    """imagefree_client.py:278 真实轮询归一化后结构。"""
    return {"status": "completed", "image": "https://r2.example.com/abc/def.png", "progress": 100}


@pytest.fixture
def imagefree_edit_mock() -> dict:
    """imagefree_client.py:415 图生图 mock 分支返回。"""
    return {"status": "completed", "image": "https://mock.example/images/edit.png"}


@pytest.fixture
def aifreeforever_images() -> dict:
    """aifreeforever.py:195-197 _generate 返回。"""
    return {"success": True, "images": ["https://aif.forevercdn.com/img/4.png"]}


# ── 有效样例通过校验 ──────────────────────────────


class TestValidSamplesPass:
    def test_imagefree_mock(self, imagefree_generate_mock):
        d = imagefree_generate_mock
        assert validate_contract(ImageGenerationResponse, d)
        assert parse_contract(ImageGenerationResponse, d) is None
        # mock 样例可带 task_id 也可不带
        d2 = {"task_id": "mock-task-1690", **d}
        assert parse_contract(ImageGenerationResponse, d2) is None

    def test_imagefree_real(self, imagefree_generate_real):
        d = imagefree_generate_real
        assert validate_contract(ImageGenerationResponse, d)
        assert probe_imagefree_poll(d) == d

    def test_imagefree_edit(self, imagefree_edit_mock):
        d = imagefree_edit_mock
        assert validate_contract(EditResponse, d)
        assert parse_contract(EditResponse, d) is None

    def test_aifreeforever_images(self, aifreeforever_images):
        urls = aifreeforever_images["images"]
        assert urls and urls[0].startswith("https://")


# ── 破坏样例立即失败 ─────────────────────────────


class TestBrokenSamplesFail:
    def test_missing_image(self):
        d = {"status": STATUS_COMPLETED, "progress": 100}
        assert not validate_contract(ImageGenerationResponse, d)
        err = parse_contract(ImageGenerationResponse, d)
        assert err is not None and "image" in err
        err2 = exact_contract_error(ImageGenerationResponse, d)
        assert err2 == err

    def test_status_wrong_enum(self):
        d = {"status": "done", "image": "https://x.example/1.png"}
        assert not validate_contract(ImageGenerationResponse, d)
        err = parse_contract(ImageGenerationResponse, d)
        assert err is not None and "status" in err

    def test_image_not_url(self):
        d = {"status": STATUS_COMPLETED, "image": "not-an-url"}
        # image 非 URL → 契约模型直接拒绝（ImageGenerationResponse，url validator）
        assert not validate_contract(ImageGenerationResponse, d)
        err = parse_contract(ImageGenerationResponse, d)
        assert err is not None and "image" in err
        # URL 探针同样应拒
        assert probe_imagefree_poll(d) is None

    def test_edit_missing_image(self):
        d = {"status": STATUS_COMPLETED}
        assert not validate_contract(EditResponse, d)
        err = parse_contract(EditResponse, d)
        assert err is not None and "image" in err

    def test_edit_wrong_status(self):
        d = {"status": "pending", "image": "https://x.example/1.png"}
        assert not validate_contract(EditResponse, d)

    def test_empty_dict(self):
        assert not validate_contract(EditResponse, {})
        err = parse_contract(EditResponse, {})
        assert err is not None and "image" in err

    def test_not_a_dict(self):
        assert not validate_contract(ImageGenerationResponse, ["x"])
        assert parse_contract(ImageGenerationResponse, None) is not None


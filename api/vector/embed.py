"""轻量 embedding 计算（无 CLIP/torch 依赖）。

设计：
- 纯 Python SimHash 风格 256 维 float 向量
- 基于 prompt token 的 hash 散布 + 累加 + L2 归一化
- 降级说明：不引入 CLIP/torch/transformers 等重型依赖（单机公益部署，零新依赖优先），
  牺牲语义精度换取零依赖开销；sqlite-vec 已是纯 Python wheel。
- 中文按字切分，英文/数字按词切分（混合 prompt 友好）
- 若需更精确语义，可后续在 IF_VECTOR_EMBED_BACKEND=clip 时懒加载（默认关闭，本实现不引入）
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import struct

log = logging.getLogger("vector")

# 向量维度：256-dim float32 = 1024 bytes/向量（轻量 + 足够区分度）
EMBED_DIM = 256

# token 切分：保留中文（一-鿿）、英文、数字；其余字符为分隔符
_TOKEN_SPLIT = re.compile(r"[^a-z0-9一-鿿]+")


def _tokenize(text: str) -> list[str]:
    """prompt 切分为 token 列表（中文按字、英文按词、统一小写）。"""
    if not text:
        return []
    text = text.lower()
    tokens: list[str] = []
    # 英文/数字词
    for word in _TOKEN_SPLIT.split(text):
        if word:
            tokens.append(word)
    # 中文按字（与英文词叠加，提升中文区分度）
    for ch in text:
        if "一" <= ch <= "鿿":
            tokens.append(ch)
    return tokens


def _hash_to_dim(token: str, dim: int, salt: bytes = b"") -> int:
    """将 token 哈希到 [0, dim) 区间（带可选盐，用于多维度散布）。"""
    h = hashlib.blake2b(token.encode(), digest_size=8, salt=salt)
    return int.from_bytes(h.digest(), "little") % dim


def compute_embedding(prompt: str, image_bytes: bytes | None = None) -> bytes:
    """计算 prompt 的 256-dim float32 embedding（BLOB）。

    Args:
        prompt: 任务 prompt 文本
        image_bytes: 可选图像字节（当前实现忽略，纯 text embedding；
            预留接口以便后续接入 pHash/CLIP，不破坏调用方）

    Returns:
        256-dim float32 little-endian BLOB（1024 bytes），L2 归一化

    Notes:
        - 空 prompt 返回固定单位向量（避免全零无法归一化）
        - token 出现次数加权（重复词权重↑）
        - 每 token 散布到 2 个维度（主+次），增加区分度
    """
    vec: list[float] = [0.0] * EMBED_DIM
    tokens = _tokenize(prompt)

    if not tokens:
        # 空 prompt：固定单位向量（首个维度=1），避免全零
        vec[0] = 1.0
        return _pack_vec(vec)

    # token 计数（重复词权重↑）
    counts: dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1

    # 双散布：每 token 投影到 2 个维度，增加区分度
    for token, cnt in counts.items():
        dim1 = _hash_to_dim(token, EMBED_DIM)
        vec[dim1] += cnt
        dim2 = _hash_to_dim(token, EMBED_DIM, salt=b"v2")
        vec[dim2] += cnt * 0.5

    # L2 归一化（cosine 相似度 = 点积，sqlite-vec L2 距离可换算）
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]

    return _pack_vec(vec)


def _pack_vec(vec: list[float]) -> bytes:
    """float32 list → little-endian BLOB。"""
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack_vec(blob: bytes) -> list[float]:
    """BLOB → float32 list。"""
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


def compute_prompt_hash(prompt: str) -> str:
    """prompt 的短哈希指纹（16 字节 hex，用于精确去重/快速查找）。

    与 embedding 的区别：embedding 用于相似度检索（KNN），
    prompt_hash 用于精确匹配（同一 prompt 一定同 hash）。
    """
    return hashlib.blake2b(prompt.encode(), digest_size=16).hexdigest()


def cosine_similarity(a: bytes, b: bytes) -> float:
    """计算两个 embedding BLOB 的余弦相似度。

    用于降级路径（sqlite-vec 不可用时的线性扫描）。
    归一化向量点积即为余弦相似度，但此处通用计算（不假设归一化）。
    """
    va = _unpack_vec(a)
    vb = _unpack_vec(b)
    if len(va) != len(vb) or not va:
        return 0.0
    dot = sum(x * y for x, y in zip(va, vb, strict=True))
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(y * y for y in vb))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def l2_distance_to_similarity(distance: float) -> float:
    """sqlite-vec L2 距离 → 余弦相似度（归一化向量）。

    对于 L2 归一化向量：‖a-b‖² = 2 - 2·cos(θ)
    故 cos(θ) = 1 - ‖a-b‖²/2 = 1 - distance²/2（sqlite-vec 返回 L2 距离，非平方）

    Args:
        distance: sqlite-vec 返回的 L2 距离（非平方，非负）

    Returns:
        余弦相似度，clamp 到 [0, 1]（负距离视为异常，按 0 处理）
    """
    if distance < 0:
        return 0.0
    sim = 1.0 - (distance * distance) / 2.0
    return max(0.0, min(1.0, sim))


__all__ = [
    "EMBED_DIM",
    "compute_embedding",
    "compute_prompt_hash",
    "cosine_similarity",
    "l2_distance_to_similarity",
]

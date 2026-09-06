"""向量检索包（P3-D1）：语义去重 + 相似图聚类。

零新重型依赖（CLIP/torch/transformers 禁入）：
- sqlite-vec（纯 Python wheel）做 KNN 检索
- embed.py 用 SimHash 风格 256-dim float 向量（纯 Python，无模型）
- sqlite-vec 不可用时降级为纯 Python 线性扫描

公共接口：
- ``from api.vector import store, embed``（向后兼容）
- ``from api.vector.store import get_vector_store, VectorStore, reset_vector_store``
- ``from api.vector.embed import compute_embedding, compute_prompt_hash, EMBED_DIM``

环境变量：
- ``IF_VECTOR_SEARCH_ENABLED``：0（缺省，关闭）/ 1（开启）
- ``IF_VECTOR_DB_FILE``：向量 DB 路径（默认 data/vectors.db）
- ``IF_VECTOR_DEDUPE_THRESHOLD``：查重相似度阈值（默认 0.95）
"""

from __future__ import annotations

from . import embed, store

__all__ = ["embed", "store"]

"""技能沉淀闭环（指南 B2 / P0-1，SkillClaw + SkillOpt 对标；手动收藏 MVP）。

职责：
- 把用户满意的 DAG run / 生成任务「保存为技能」→ 草稿（draft）
- 保存前强制过安全扫描（skill_scan.scan_skill，B1b 闸门）：risk_score >= 阈值拒绝入库
- 审批（approve/reject）后成为「我的技能」，可被复用/展示

存储：独立 SQLite ``data/skills.db``（与 ``data/dag_runs.db`` 同模式：独立文件、线程安全由
aiosqlite + 单 asyncio loop 保证、内存降级缓存保活）。

开关：IF_SKILL_SEDIMENT_ENABLED=1 时路由层才暴露保存端点（缺省 0，零行为变化）。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

import aiosqlite

log = logging.getLogger("agent.skill_sediment")

def _default_db() -> str:
    """动态读 env（模块导入期固化会导致测试/部署切换 DB 失效）。"""
    return os.getenv("IF_SKILL_SEDIMENT_DB", "data/skills.db")

_STATUS_DRAFT = "draft"
_STATUS_APPROVED = "approved"
_STATUS_REJECTED = "rejected"
VALID_STATUSES = (_STATUS_DRAFT, _STATUS_APPROVED, _STATUS_REJECTED)


def build_skill_md(*, name: str, description: str, prompt_template: str, params: dict[str, Any], notes: str) -> str:
    """把 run 快照固化为 SKILL.md 格式（frontmatter + body，与 api/skills/loader 兼容）。"""
    safe_name = re.sub(r"[^A-Za-z0-9_-]", "-", name.strip()).strip("-") or "untitled-skill"
    safe_desc = (description or "由 DAG run 沉淀的个人技能").strip()
    params_json = json.dumps(params, ensure_ascii=False, indent=2) if params else "{}"
    body = f"""## 触发条件

- 用户表达相似意图 / 复用该工作流时（保存自 run 的个人技能）

## 工作流（沉淀快照）

1. 提示词模板（可复用）：
```
{prompt_template}
```

2. 结构化参数：
```json
{params_json}
```

## 备注

{notes or "（无）"}

## 来源

- 保存方式：手动收藏（MVP）
- 审批状态：草稿，需管理员审批后生效
"""
    return (
        "---\n"
        f"name: {safe_name}\n"
        f"description: {safe_desc[:200]}\n"
        "version: 1.0.0\n"
        "security:\n"
        "  run: isolated\n"
        "  network: none\n"
        "  approvals: admin\n"
        "inputs:\n"
        "  prompt: string 必填 触发提示词\n"
        "outputs:\n"
        "  result: string 技能执行结果\n"
        "---\n"
        f"{body}"
    )


class SkillSedimentStore:
    """技能沉淀存储（独立 SQLite：data/skills.db）。"""

    def __init__(self, path: str | None = None) -> None:
        self.path = path or _default_db()
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        self._memory: dict[str, dict[str, Any]] = {}

    async def _ensure_open(self) -> aiosqlite.Connection:
        if self._db is not None:
            return self._db
        parent = Path(self.path).parent
        if parent and str(parent) != ".":
            parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS skills (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                prompt_template TEXT NOT NULL,
                params TEXT NOT NULL DEFAULT '{}',
                source_run_id TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                risk_score INTEGER NOT NULL DEFAULT 0,
                scan_findings TEXT NOT NULL DEFAULT '[]',
                notes TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                approved_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status);
            CREATE TABLE IF NOT EXISTS skill_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                content TEXT NOT NULL,
                checksum TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            """
        )
        await self._db.commit()
        return self._db

    async def _close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def save_draft(
        self,
        *,
        name: str,
        description: str,
        prompt_template: str,
        params: dict[str, Any],
        source_run_id: str | None,
        risk_score: int,
        scan_findings: list[dict[str, Any]],
        notes: str = "",
    ) -> dict[str, Any]:
        """保存技能草稿。重复 name 抛 ValueError（唯一约束）。"""
        async with self._lock:
            db = await self._ensure_open()
            now = time.time()
            existing = await self.get_by_name(name.strip())
            if existing is not None:
                raise ValueError(f"技能名已存在: {name.strip()}")
            skill_id = uuid.uuid4().hex
            content = build_skill_md(
                name=name,
                description=description,
                prompt_template=prompt_template,
                params=params,
                notes=notes,
            )
            checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
            await db.execute(
                "INSERT INTO skills (id, name, description, prompt_template, params, source_run_id,"
                " status, risk_score, scan_findings, notes, created_at, updated_at, approved_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    skill_id,
                    name.strip(),
                    description,
                    prompt_template,
                    json.dumps(params, ensure_ascii=False),
                    source_run_id,
                    _STATUS_DRAFT,
                    int(risk_score),
                    json.dumps(scan_findings, ensure_ascii=False),
                    notes,
                    now,
                    now,
                    None,
                ),
            )
            await db.execute(
                "INSERT INTO skill_versions (skill_id, version, content, checksum, created_at)"
                " VALUES (?,?,?,?,?)",
                (skill_id, 1, content, checksum, now),
            )
            await db.commit()
            row = await self.get_skill(skill_id)
            if row is None:
                raise RuntimeError("技能保存后读取失败")
            return row

    async def get_skill(self, skill_id: str) -> dict[str, Any] | None:
        db = await self._ensure_open()
        cur = await db.execute(
            "SELECT id, name, description, prompt_template, params, source_run_id, status,"
            " risk_score, scan_findings, notes, created_at, updated_at, approved_at"
            " FROM skills WHERE id = ?",
            (skill_id,),
        )
        row = await cur.fetchone()
        return self._row_to_dict(row) if row is not None else None

    async def get_by_name(self, name: str) -> dict[str, Any] | None:
        db = await self._ensure_open()
        cur = await db.execute("SELECT * FROM skills WHERE name = ?", (name,))
        row = await cur.fetchone()
        return self._row_to_dict(row) if row is not None else None

    async def list_skills(self, status: str | None = None) -> list[dict[str, Any]]:
        db = await self._ensure_open()
        if status:
            cur = await db.execute(
                "SELECT * FROM skills WHERE status = ? ORDER BY updated_at DESC", (status,)
            )
        else:
            cur = await db.execute("SELECT * FROM skills ORDER BY updated_at DESC")
        rows = await cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def set_status(self, skill_id: str, status: str) -> bool:
        """更新状态（approve/reject），返回是否命中。"""
        if status not in VALID_STATUSES:
            raise ValueError(f"非法状态: {status}")
        async with self._lock:
            db = await self._ensure_open()
            now = time.time()
            approved_at = now if status == _STATUS_APPROVED else None
            cur = await db.execute(
                "UPDATE skills SET status = ?, updated_at = ?, approved_at = ? WHERE id = ?",
                (status, now, approved_at, skill_id),
            )
            await db.commit()
            return cur.rowcount > 0

    async def delete_skill(self, skill_id: str) -> bool:
        async with self._lock:
            db = await self._ensure_open()
            await db.execute("DELETE FROM skill_versions WHERE skill_id = ?", (skill_id,))
            cur = await db.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
            await db.commit()
            return cur.rowcount > 0

    async def close(self) -> None:
        await self._close()

    @staticmethod
    def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
        d = dict(row)
        for k in ("params", "scan_findings"):
            if isinstance(d.get(k), str):
                try:
                    d[k] = json.loads(d[k])
                except (TypeError, ValueError):
                    d[k] = {}
        return d


# 模块级单例（测试可用 reset 重建）
skill_sediment_store = SkillSedimentStore()


def reset_store() -> None:
    """测试钩子：重置单例（丢弃连接与内存缓存）。"""
    global skill_sediment_store
    skill_sediment_store = SkillSedimentStore()


__all__ = [
    "SkillSedimentStore",
    "build_skill_md",
    "reset_store",
    "skill_sediment_store",
]

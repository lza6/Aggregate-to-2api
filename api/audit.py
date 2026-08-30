"""不可变审计日志（仅追加），记录管理操作、鉴权失败、provider 状态变更等。

B2: record 支持 trace_id 透传，写入 JSON 行的 trace_id 字段，可 grep 串联。
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("imagefree_api.audit")


class AuditLog:
    """不可变审计日志。仅追加写入，永不修改已有记录。"""

    def __init__(self, path: str = "data/audit.log"):
        self._path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    def record(self, action: str, actor: str, target: str,
               detail: str | None = None, trace_id: str | None = None) -> None:
        # B2: trace_id 缺省时取当前请求上下文（无活跃请求则空串）
        if trace_id is None:
            try:
                from .context import get_current_trace_id
                trace_id = get_current_trace_id() or ""
            except Exception:
                trace_id = ""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "actor": actor,
            "target": target,
            "detail": detail,
            "trace_id": trace_id,
        }
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            log.warning("审计日志写入失败: %s", e)

    def recent(self, limit: int = 50) -> list[dict]:
        try:
            with open(self._path, encoding="utf-8") as f:
                lines = f.readlines()
        except (OSError, FileNotFoundError):
            return []
        entries = []
        for line in lines[-limit:]:
            try:
                entries.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
        return entries


# 全局单例
audit_log = AuditLog()

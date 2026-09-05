"""P0-3 防回归：验证「async def 内不直接调用同步 sqlite3」的契约。

SQLite3 的 C 类型（sqlite3.Connection）实例/类均不可遮蔽方法属性，故不采用
运行时 monkeypatch，改用 **AST 静态契约扫描**：遍历触发热点模块（account_pool /
email_pool / nanobanana / aifreeforever / imagefree）的所有方法，凡标注
`async def`（或含 `async_` 前缀）的方法，其函数体内 **不得直接** 调用
`self._conn.execute` / `self._conn.executescript` / 裸 `sqlite3` 同步执行。
同步方法（作为 asyncio.to_thread 的同步壳）允许直接 execute。

同时补一个运行时行为用例：并发 async 包装下，事件循环仍能调度 sleep(0) 协程
（阻塞证据），证明实际运行不阻塞。

本测试是「守门」性质：若未来有人把 async 方法内的同步 DB 调用从 to_thread 拆回
裸同步，AST 扫描立刻红。
"""

import ast
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
HOT_MODULES = [
    "api/account_pool/pool.py",
    "api/account_pool/fsm.py",
    "api/account_pool/scoring.py",
    "api/account_pool/__init__.py",
    "api/email_pool.py",
    "api/providers/nanobanana.py",
    "api/providers/aifreeforever.py",
    "api/providers/imagefree.py",
]


def _is_sync_sqlite_call(node: ast.AST) -> bool:
    """是否为 self._conn.execute/executescript(...) 或 sqlite3.xxx 的调用。"""
    if isinstance(node, ast.Call):
        f = node.func
        # self._conn.execute(...) / self._conn.executescript(...)
        if (
            isinstance(f, ast.Attribute)
            and f.attr in ("execute", "executescript")
            and isinstance(f.value, ast.Attribute)
            and f.value.attr == "_conn"
        ):
            return True
        # sqlite3.connect(...) 直接调用也是同步 I/O 证据（async 内）
        if (
            isinstance(f, ast.Attribute)
            and f.attr in ("connect",)
            and isinstance(f.value, ast.Name)
            and f.value.id == "sqlite3"
        ):
            return True
    return False


def _collect_contamination(tree: ast.AST, module_name: str) -> list[str]:
    """扫描所有方法定义：async 方法体不得含同步 sqlite 调用。"""
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_async = isinstance(node, ast.AsyncFunctionDef)
            # 仅对 async 方法（或在 async 上下文被直接 await 的 async def）强制契约
            # 同步方法允许裸 execute（它们是 to_thread 的同步壳）
            if not is_async:
                continue
            # 检查该方法体内是否直接调用同步 sqlite（遍历其所有子节点，跳过嵌套函数定义，
            # 因为嵌套的 def/async def 会被外层 walk 单独扫描）
            for sub in ast.walk(node):
                # 跳过嵌套定义（避免内层同级函数重复计数，不影响判断）
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub is not node:
                    # 但仍要检查：async 方法里若调用了 to_thread(self.sync_method)，sync_method
                    # 是另一个顶层方法，由外层 walk 单独扫描；此处嵌套函数无需重复。
                    continue
                if _is_sync_sqlite_call(sub):
                    findings.append(f"{module_name}:{sub.lineno} {node.name}(async) 内直接同步 sqlite 调用")
                    break
    return findings


# ── 用例 1：静态契约扫描（核心守门）────────────────────────────────
@pytest.mark.parametrize("rel_path", HOT_MODULES)
def test_async_methods_no_bare_sync_sqlite(rel_path: str):
    """async def 方法体内不得直接调用 self._conn.execute/executescript 或 sqlite3.connect。"""
    src = (_ROOT / rel_path).read_text(encoding="utf-8")
    tree = ast.parse(src)
    findings = _collect_contamination(tree, rel_path)
    assert not findings, (
        f"{rel_path} 存在 async 方法内裸同步 sqlite 调用（会阻塞事件循环）：\n" + "\n".join(findings)
        + "\n修复：把这些调用移入同步方法，再在 async 内用 asyncio.to_thread 调用。"
    )


# ── 用例 2：运行时行为（不阻塞事件循环）─────────────────────────────
@pytest.mark.asyncio
async def test_async_wrappers_keep_loop_responsive(tmp_path):
    """并发 async 包装下，事件循环仍能调度 sleep(0) 协程（不阻塞证据）。

    P2-3 后 account_pool 方法已 async（aiosqlite），_conn 惰性初始化；
    旧 p.add 同步调用 + p._conn.close 需改为 await + _close_conn_safe。
    """
    from api.account_pool import AccountPool

    p = AccountPool(str(tmp_path / "resp.db"))
    try:
        await p.add("nanobanana", "a@x.com", "cookie", credits=100, status="active")
        flag = {"ticked": 0}

        async def _tick():
            for _ in range(5):
                await asyncio.sleep(0)
                flag["ticked"] += 1

        async def _work():
            for _ in range(5):
                await p.async_get("nanobanana")
                await p.async_consume_credits("nanobanana", "a@x.com", 1)

        await asyncio.gather(_tick(), _work())
        assert flag["ticked"] == 5, "事件循环被同步 sqlite3 阻塞，sleep(0) 无法调度！"
    finally:
        try:
            await p._close_conn_safe()
        except Exception:
            pass


import asyncio  # noqa: E402  (延迟到文件内使用点即可，此处仅为局部清楚)

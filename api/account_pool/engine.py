"""AccountPool 自动补号/巡检循环 mixin（P0-F2 拆分）。

从 pool.py 拆出：start/_autoreg_enabled/stop/_cooling_wake_loop/_autoregister_loop。
方法签名/SQL/列名全部不变，仅物理位置迁移到本 mixin。

被 monkeypatch 的常量（TARGET_NANOBANANA/REGISTER_COOLDOWN/MOCK_REGISTER）
经 `_pkg_attr()` 运行时读包命名空间，保持 `monkeypatch.setattr(...)` 命中。
"""

from __future__ import annotations

import asyncio
import os

from ..proxy_pool import proxy_pool
from ._constants import (
    MOCK_REGISTER,
    REGISTER_COOLDOWN,
    TARGET_NANOBANANA,
    _pkg_attr,
    log,
)


class EngineMixin:
    """自动补号/签到/延寿唤醒巡检 mixin，由 AccountPool 多继承组合。"""

    # ── 自动补号 / 签到 / 延寿唤醒循环 ────────────────────────
    async def start(self) -> None:
        # 为长效签到型提供商（nanobanana）开启自动补号与延寿巡检
        auto_provs = [p for p in ("nanobanana",) if self._autoreg_enabled(p)]
        for prov in auto_provs:
            self.checkin_tasks[f"register:{prov}"] = asyncio.create_task(self._autoregister_loop(prov))
        # 每日签到与自动延寿巡检器
        self.checkin_tasks["nanobanana_checkin"] = asyncio.create_task(self._daily_checkin_loop("nanobanana"))
        self.checkin_tasks["wake_inspector"] = asyncio.create_task(self._cooling_wake_loop())
        log.info("号池 FSM 引擎启动：自动补号 %s + 签到与延寿唤醒巡检器就绪", auto_provs)

    @staticmethod
    def _autoreg_enabled(provider: str) -> bool:
        return os.getenv("IF_NANOBANANA_AUTOREG", "1").strip().lower() in {"1", "true", "yes", "on"}

    async def stop(self) -> None:
        for t in self.checkin_tasks.values():
            t.cancel()
        if self.checkin_tasks:
            await asyncio.gather(*self.checkin_tasks.values(), return_exceptions=True)
        self.checkin_tasks.clear()
        await self._close_conn_safe()

    async def _cooling_wake_loop(self) -> None:
        """延寿唤醒巡检：每 5 分钟先回收超租约 working 账号，再扫描冷却账号并自动唤醒恢复。"""
        while True:
            try:
                await asyncio.sleep(300)
                for prov in ("nanobanana",):
                    # P2-3: 方法已 async，直接 await（不再 to_thread）
                    await self._reclaim_lease_timeout(prov)
                    await self.wake_cooling_accounts(prov)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("延寿唤醒巡检器异常: %s", e)

    async def _autoregister_loop(self, provider: str) -> None:
        """提供商自动补号守护任务。"""
        while True:
            try:
                if not await self._can_fill(provider):
                    await asyncio.sleep(60)
                    continue
                await self._register_one_now(provider)
                await asyncio.sleep(_pkg_attr("REGISTER_COOLDOWN", REGISTER_COOLDOWN))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("号池补号循环异常 %s: %s", provider, e)
                await asyncio.sleep(30)

    async def _can_fill(self, provider: str) -> bool:
        """补号判定纯函数（P2-11 flaky 根治）：当前可用号 < 目标 且 有注册器 且 可补。

        从 _autoregister_loop 抽出，测试可脱离无限循环时序直接断言：
        - 可用号 >= 目标 → False（已满）
        - 无注册器 → False
        - 非 mock 模式且代理池为空 → False（无代理守卫生效，避免误注册）
        """
        try:
            usable = len(await self.get(provider))
        except Exception:
            return False
        target = _pkg_attr("TARGET_NANOBANANA", TARGET_NANOBANANA)
        if usable >= target or self.registerers.get(provider) is None:
            return False
        if not _pkg_attr("MOCK_REGISTER", MOCK_REGISTER) and not proxy_pool.entries:
            return False
        return True

    async def _register_one_now(self, provider: str) -> bool:
        """补号单步（P2-11 flaky 根治）：注册一个账号并入库，返回是否成功。

        循环与测试共用同一实现（不复制注册逻辑）：acquire 代理 → register_one →
        add + mark ok。异常吞掉返回 False（与旧循环 except 分支等价）。
        """
        reg = self.registerers.get(provider)
        if reg is None:
            return False
        try:
            reg.proxy = await proxy_pool.acquire()
            acc = await reg.register_one()
            if not acc:
                return False
            await self.add(
                provider,
                acc["email"],
                acc["cookie"],
                acc.get("password"),
                credits=acc.get("credits", 0),
                register_ip=acc.get("register_ip", ""),
            )
            await self.mark(provider, acc["email"], "ok")
            return True
        except Exception as e:
            log.warning("号池补号失败 %s: %s", provider, e)
            return False

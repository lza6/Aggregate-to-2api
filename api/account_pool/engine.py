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
        target = _pkg_attr("TARGET_NANOBANANA", TARGET_NANOBANANA)
        while True:
            try:
                usable = len(await self.get(provider))
                if usable >= target:
                    await asyncio.sleep(60)
                    continue
                reg = self.registerers.get(provider)
                if reg is None:
                    await asyncio.sleep(30)
                    continue

                try:
                    if not _pkg_attr("MOCK_REGISTER", MOCK_REGISTER):
                        # 号池注册需轮换 IP：只要池里有任何代理就尝试 acquire（内部按冷却分配）。
                        # 不能用 available()（受 IF_PROXY_MAX_USE_PER_DAY=1 每日限额约束）做前置判定，
                        # 否则用一轮后全部 use_count=1 会被误判"无可用代理"而永久暂停。
                        if not proxy_pool.entries:
                            log.info("号池补号暂停 %s：代理池为空（抓取器尚未注入）", provider)
                            await asyncio.sleep(_pkg_attr("REGISTER_COOLDOWN", REGISTER_COOLDOWN))
                            continue
                    reg.proxy = await proxy_pool.acquire()
                    acc = await reg.register_one()
                    if acc:
                        await self.add(
                            provider,
                            acc["email"],
                            acc["cookie"],
                            acc.get("password"),
                            credits=acc.get("credits", 0),
                            register_ip=acc.get("register_ip", ""),
                        )
                        await self.mark(provider, acc["email"], "ok")
                        log.info(
                            "号池补号成功 %s: %s（现有 %d）", provider, acc["email"], len(await self.get(provider))
                        )
                        await asyncio.sleep(_pkg_attr("REGISTER_COOLDOWN", REGISTER_COOLDOWN))
                    else:
                        await asyncio.sleep(_pkg_attr("REGISTER_COOLDOWN", REGISTER_COOLDOWN))
                except Exception as e:
                    log.warning("号池补号失败 %s: %s", provider, e)
                    await asyncio.sleep(_pkg_attr("REGISTER_COOLDOWN", REGISTER_COOLDOWN))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("号池补号循环异常 %s: %s", provider, e)
                await asyncio.sleep(30)

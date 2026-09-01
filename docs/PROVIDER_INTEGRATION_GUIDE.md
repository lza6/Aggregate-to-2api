# 提供商接入指南（Provider Integration Guide）

本文档说明如何为听风AI 网关接入一个新的上游图像/对话提供商。目标读者：维护者本人（降低未来接入新上游的认知成本）。

参考实现：
- **免费无需账号**：`api/providers/imagefree.py`（`ImagefreeProvider`）
- **积分制需账号**：`api/providers/nanobanana.py`（`NanobananaProvider`，每日签到续额）
- **可选聊天提供商**：`api/providers/tryingopen.py`（`ChatProvider` 子类）

---

## 1. Provider 抽象基类

所有图像提供商继承 `api/providers/base.py:Provider`（抽象基类）。核心契约：

```python
class Provider(abc.ABC):
    prefix: str = "base"           # 唯一前缀，模型 id 用（如 "nanobanana"）
    display_name: str = "Base"     # 前端看板显示名
    base_url: str = ""             # 上游站点
    models: dict[str, ModelSpec] = {}  # 该提供商支持的模型（id → ModelSpec）

    def __init__(self, config: dict | None = None) -> None: ...
    async def startup(self) -> None: ...   # 启动钩子：加载号池/代理池/签到循环
    async def shutdown(self) -> None: ... # 停止钩子：取消后台任务、关连接

    def supports(self, capability: str) -> bool: ...  # 是否支持某能力（txt2img/img2img/...）

    @abc.abstractmethod
    async def generate(self, model, prompt, aspect_ratio, images=None,
                       resolution="1K", download=False, **kw) -> GenerationResult: ...

    async def credits(self) -> int | None: ...     # 可选：当前额度（None=不适用）
    async def health(self) -> dict: ...            # 可选：健康/风控摘要（healthz 用）
    async def health_check(self) -> str: ...       # 可选：健康探测，返回 healthy/degraded/down

    def needs_proxy_per_request(self) -> bool: ...  # 每 IP 限额的平台必须 True
    def needs_account(self) -> bool: ...           # 积分制/用完即丢平台必须 True
```

`ModelSpec`（统一模型描述，`base.py:ModelSpec`）：

```python
@dataclass(frozen=True)
class ModelSpec:
    id: str                          # 外部 id = "<prefix>/<upstream_model>"
    provider: str                    # 提供商前缀
    upstream_model: str              # 上游真实模型 id
    capabilities: tuple[str, ...]   # txt2img / img2img / txt2vid / img2vid
    display_name: str = ""
    description: str = ""
    aspect_ratios: tuple[str, ...] = ("1:1", "3:4", "4:3", "9:16", "16:9")
    resolutions: tuple[str, ...] = ("1K", "2K", "4K")
    credits: int | None = None       # 上游积分费率（None=不适用）
    account_required: bool = False   # 是否需要号池账号
    meta: dict[str, Any] = field(default_factory=dict)
```

**命名契约（CRITICAL）**：外部模型 `id = "<provider_prefix>/<upstream_model>"`，例 `nanobanana/nano-banana-pro`、`imagefree/default`。这是 `/v1/models` 与路由查找的硬契约。

---

## 2. 必需实现的方法

### 2.1 `generate()`（抽象，必须实现）

```python
@abc.abstractmethod
async def generate(self, model, prompt, aspect_ratio, images=None,
                   resolution="1K", download=False, **kw) -> GenerationResult:
    """统一生成入口。images 非空=图生图（capability 需含 img2img）。"""
```

返回 `GenerationResult`（`base.py:GenerationResult`）：

```python
@dataclass
class GenerationResult:
    status: str                      # "completed" | "error"
    asset_url: str | None = None     # 产物 URL（二选一）
    asset_bytes: bytes | None = None # 产物字节（download=True 时填）
    asset_mime: str | None = None
    error: str | None = None         # status=error 时填面向用户的消息
    raw: dict | None = None         # 原始上游响应（调试用）
    proxy_used: str | None = None   # 该请求出口代理（轮换代理的提供商填）
```

异常：
- `ProviderError`：业务错误（上游 5xx / 解析失败 / 风控），调用方据消息重试。
- `ProviderRateLimited`：上游限流（429 / 频控），`is_transient` 决定重试。

### 2.2 `health()`（可选覆写）

默认返回 `{"healthy": True, "note": ""}`。积分制提供商应覆写返回真实余额与状态：

```python
async def health(self) -> dict:
    return {"healthy": self.health_status == "healthy", "credits": await self.credits()}
```

### 2.3 `credits()`（可选覆写）

积分制提供商返回当前可用额度（int），免费提供商返回 `None`。

---

## 3. 健康检查契约

`Provider` 内置 `health_status` 状态机（`base.py:88`）：

| 状态 | 含义 | 由谁设置 |
|------|------|----------|
| `unknown` | 未探测 | 初始值 |
| `healthy` | 健康 | `mark_up()` / `health_check()` |
| `degraded` | 部分可用（限流/降级） | `registry.record_failure()` |
| `down` | 不可用 | `mark_down()` / `health_check()` |

`registry.py` 维护 `provider_health: dict[str, str]`，降级/熔断逻辑：

- 连续 `ProviderRateLimited` 累计（`_consecutive_failures`）→ `degraded`
- 持续失败 → `down` + 恢复探测退避（`_last_recover_at`）
- 账号耗尽（`_exhausted_accounts`）→ 该账号不再借出

`health_check()` 默认返回 `"healthy"`，子类可覆写实现具体探测（如调上游 `/health` 端点）。

---

## 4. credits 积分制（needs_account=True 的提供商）

适用：nanobanana-pro 等每日签到续额的积分制平台。

### 4.1 AccountPool 集成

`needs_account()` 返回 `True` 时，`registry` 会从 `account_pool`（`api/account_pool.py`）借号/归还：

```python
def needs_account(self) -> bool:
    return any(m.account_required for m in self.models.values())
```

`generate()` 内典型流程：

```python
async def generate(self, model, prompt, ...):
    acc = await account_pool.async_borrow_account(self.prefix)  # 借号（互斥）
    try:
        result = await self._upstream_generate(acc, prompt, ...)
        await account_pool.async_consume_credits(self.prefix, acc["email"], credits_cost)
        return GenerationResult(status="completed", asset_url=result.url)
    except ProviderRateLimited:
        await account_pool.async_mark_dead(self.prefix, acc["email"], "rate limited")
        raise
    finally:
        await account_pool.async_release_account(self.prefix, acc["email"])
```

### 4.2 每日签到

积分制提供商应在 `startup()` 启动签到循环（`account_pool.checkin_tasks`），每日自动签到续额。参考 `nanobanana.py` 的 `ActionSniffer` 动态嗅探 Action ID + 静态兜底。

---

## 5. 路由注册（registry.bootstrap）

新提供商在 `api/providers/registry.py:bootstrap()` 注册：

```python
def bootstrap() -> None:
    if registry._booted:
        return
    registry.register(imagefree.ImagefreeProvider())
    registry.register(aifreeforever.AifreeforeverProvider())
    registry.register(nanobanana.NanobananaProvider())
    # 可选提供商（开关控制）
    if config.IF_FALAI_ENABLED:
        try:
            from .falai import FalaiProvider
            registry.register(FalaiProvider())
        except Exception as e:
            log.warning("提供商 falai 注册失败（降级跳过）: %s", e)
    # ... tryingopen chat provider
    registry._booted = True
```

- `registry.register(provider)`：注册图像 Provider，自动收集其 `models` 到 `_models`。
- `registry.register_chat(provider)`：注册聊天 `ChatProvider`（`base.py:ChatProvider`，与图像 Provider 平行）。
- 可选提供商用 `IF_XXX_ENABLED` 开关包裹 + `try/except` 降级跳过（注册失败不阻塞其他提供商）。

---

## 6. 降级契约（degraded → select_best MAB 打分）

`registry.provider_for(model_id)` 路由逻辑（v3.2 起）：

1. **healthy 路径**：用户 `model_id` 前缀即提供商，直接返回该 provider（**不跨商偷换**，除非用户显式用聚合模型 id 如 `default`）。
2. **degraded 路径**（首选 provider 不可用）：`find_alternatives(model_id)` 返回全部能力匹配的健康备用（按能力重叠数降序）。
   - `len(alts) > 1` → `adaptive_router.select_best([p.prefix...], model=model_id, requested_provider=spec.provider)` 用 MAB-EWMA 打分选最优。
   - `len(alts) == 1` → 直接返回单备用（单候选无打分意义）。
   - `alts == []` → 直连首选 + `record_direct`。
3. **熔断**：`down` 状态的 provider 不参与候选，恢复探测退避后才重新进入。

`select_best`（`api/adaptive_router.py:492`）用 EMA 延迟 + 成功率 + Laplace 平滑打分，healthy 路径不调用（仅 degraded 多候选调用）。

---

## 7. 测试要求（providers_contract）

新提供商必须通过 `tests/test_providers_contract.py` 契约测试（防上游悄悄改结构）：

- 用真实历史响应样例（最小但真实 dict）做 fixture。
- 有效样例通过 `validate_contract` / `parse_contract` 校验。
- 破坏样例（删 image / status 错枚举 / image 非 URL）立即失败且能 tell 缺字段。

新增提供商时：
1. 在 `api/contracts.py` 加该提供商的 `parse_xxx_poll` / `validate_contract` 适配。
2. 在 `tests/test_providers_contract.py` 加 fixture（真实响应样例）+ 有效/破坏用例。

其他建议测试：
- `tests/test_providers_health.py`：健康检查状态机。
- `tests/test_adaptive_router.py`：降级路由 select_best（多候选/单候选/无备用）。
- 集成测试：`IF_MOCK_UPSTREAM=1` 跑 generate 全链路（不真实调上游）。

---

## 8. 配置项（IF_ 前缀环境变量）

所有配置用 `IF_` 前缀环境变量，在 `api/config/__init__.py:Settings` 或子配置类声明：

| 配置 | 默认 | 用途 |
|------|------|------|
| `IF_XXX_ENABLED` | `0` | 可选提供商开关（falai/tryingopen） |
| `IF_XXX_BASE_URL` | 上游站点 | 提供商上游 URL |
| `IF_XXX_ACCOUNT_TARGET` | 平台限额 | 积分制目标常驻账号数 |
| `IF_REGISTER_COOLDOWN` | `90` | 补号退避（秒，防风控） |
| `IF_ACCOUNT_COOLING_PERIOD` | `72000` | 账号冷却期（秒，20h） |
| `IF_MOCK_REGISTER` | `0` | 测试期 mock 注册（生产必须 0） |
| `IF_MOCK_UPSTREAM` | `0` | 测试期 mock 上游响应 |
| `IF_FREE_PROXY` | `0` | 免费代理池（每 IP 限额平台必须 1） |

新增提供商配置时：
1. 在 `Settings` 类加 `Field(default, validation_alias="IF_XXX_...")`。
2. 在 `deploy/.env.example` 加注释说明。
3. 生产开启需在 `deploy/docker-compose.yml` api environment 加该 env。

---

## 9. 参考实现对比

### imagefree（免费无需账号）

```python
class ImagefreeProvider(Provider):
    prefix = "imagefree"
    display_name = "imagefree（主站）"

    def __init__(self, config=None):
        super().__init__(config)
        for mid, (name, desc, caps, _prefix) in _PRESETS.items():
            self.models[mid] = ModelSpec(
                id=f"{self.prefix}/{mid}",
                provider=self.prefix,
                upstream_model=mid,
                capabilities=caps,
                display_name=name,
            )

    def needs_account(self) -> bool:
        return False  # 免费无需账号

    async def generate(self, model, prompt, aspect_ratio, ...):
        # 直接调上游，无需借号
        ...
```

特点：
- `needs_account() = False`，不集成 AccountPool。
- `credits() = None`（理论无限）。
- 无签到循环，`startup()` 仅初始化 HTTP 客户端。

### nanobanana（积分制需账号）

```python
class NanobananaProvider(Provider):
    prefix = "nanobanana"
    display_name = "Nano Banana Pro（每日签到）"

    def __init__(self, config=None):
        super().__init__(config)
        self.action_sniffer = ...  # 动态嗅探 Action ID
        for mid, spec in _MODELS.items():
            self.models[mid] = ModelSpec(..., account_required=True, credits=spec.credits)

    def needs_account(self) -> bool:
        return True  # 积分制必须借号

    async def generate(self, model, prompt, ...):
        acc = await account_pool.async_borrow_account(self.prefix)
        try:
            ...  # 用 acc cookie 调上游
            await account_pool.async_consume_credits(...)
            return GenerationResult(...)
        finally:
            await account_pool.async_release_account(...)
```

特点：
- `needs_account() = True`，集成 AccountPool（借号/归还/扣积分/封号标记）。
- `startup()` 启动签到循环（每日自动签到续额）。
- `ActionSniffer` 动态嗅探上游 Action ID（站点改版自动适应），静态兜底值仅在嗅探失败时用。
- `credits()` 返回真实余额。
- `health()` 返回 `{"healthy": ..., "credits": ...}`。

---

## 10. 接入新提供商 Checklist

- [ ] 新建 `api/providers/<name>.py`，继承 `Provider`（或 `ChatProvider`）。
- [ ] 设置 `prefix` / `display_name` / `base_url` / `models`。
- [ ] 实现 `generate()`（抽象必须）。
- [ ] 覆写 `health()` / `credits()`（积分制必须）。
- [ ] 覆写 `needs_account()` / `needs_proxy_per_request()`（按平台特性）。
- [ ] 在 `registry.bootstrap()` 注册（可选提供商加 `IF_XXX_ENABLED` 开关 + try/except 降级）。
- [ ] 在 `api/contracts.py` 加该提供商响应契约 + `tests/test_providers_contract.py` 加 fixture。
- [ ] 在 `api/config/__init__.py` 加 `IF_XXX_*` 配置项 + `deploy/.env.example` 注释。
- [ ] 跑 `pytest tests/test_providers_contract.py tests/test_providers_health.py tests/test_adaptive_router.py` 全绿。
- [ ] `IF_MOCK_UPSTREAM=1` 跑集成测试（不真实调上游）。
- [ ] 更新本文档「参考实现对比」章节。

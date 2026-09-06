# Cloudflare 免费层接入指南（P1-O3）

> **目标**：landing/admin 静态资源全球边缘缓存 + DDoS 防护 + WAF + 边缘限流。
>
> **前置条件**：`imagefree.tingfengai.art` 域名可迁移 NS 至 Cloudflare（需用户拍板，属 L3 生产灰度）。
>
> **风险等级**：L3（生产灰度 + 外部资源，未授权不实施）

---

## 0. 决策清单（实施前必须确认）

| 项 | 决策 | 说明 |
|---|---|---|
| 域名 NS 迁移 | ☐ 用户拍板 | `imagefree.tingfengai.art` 的 NS 记录迁至 Cloudflare，DNS 托管转移 |
| 当前 DNS 提供商 | ☐ 确认 | 腾讯云 DNSPod 或其他，需切 NS |
| 橙云代理开启 | ☐ 确认 | 静态资源走 CF 代理；API 可按需灰云直连 |
| SSL 模式 | ☐ Full(strict) | 源站已有 Caddy + 有效证书，用 Full(strict) 防中间人 |

---

## 1. DNS 托管迁移

### 1.1 添加站点到 Cloudflare

1. Cloudflare 控制台 → Add a Site → 输入 `tingfengai.art`
2. 选择 **Free 计划**
3. CF 自动扫描现有 DNS 记录 → 核对：
   - `imagefree` A 记录 → 腾讯云东京源站 IP
   - `landing` CNAME（如有）→ 同源站
4. CF 给出两个 NS：`xxx.ns.cloudflare.com`
5. 到当前域名注册商（腾讯云/阿里云）改 NS 为 CF 的两个 NS
6. 等待 NS 生效（最长 24h，通常 10-30min）

### 1.2 验证

```bash
# NS 生效后
dig NS tingfengai.art +short  # 应返回 xxx.ns.cloudflare.com
dig imagefree.tingfengai.art +short  # 应返回 CF 代理 IP（104.x / 172.67.x）
```

---

## 2. Cache Rules（边缘缓存策略）

### 2.1 静态资源 Cache Everything

**规则1：管理面板静态资源**
- 匹配：`(http.host eq "imagefree.tingfengai.art" and starts_with(http.request.uri.path, "/admin/assets/"))`
- 缓存：Cache Everything
- Edge TTL：1 day（或 respect origin）
- Browser TTL：1 hour

**规则2：landing 静态资源**
- 匹配：`(http.host eq "imagefree.tingfengai.art" and (starts_with(http.request.uri.path, "/assets/") or starts_with(http.request.uri.path, "/fonts/")))`
- 缓存：Cache Everything
- Edge TTL：7 days

**规则3：favicon / robots / sitemap**
- 匹配：`(http.request.uri.path in {"/favicon.ico" "/robots.txt" "/sitemap.xml"})`
- 缓存：Cache Everything，Edge TTL 1 day

### 2.2 API 路径 Bypass（不缓存）

**规则4：API + SSE + WS 不缓存**
- 匹配：`(starts_with(http.request.uri.path, "/v1/") or ends_with(http.request.uri.path, "/ws") or ends_with(http.request.uri.path, "/events"))`
- 缓存：Bypass Cache（**CRITICAL：防 SSE 实时性丢失**）

> **禁区**：SSE 端点（`/v1/tasks/{id}/events`、`/v1/events/tasks`）和 WS 端点（`/v1/tasks/{id}/ws`）必须 bypass。CF 免费层对 SSE 默认缓冲 100s，会导致实时推送延迟。Bypass 规则确保流式端点直连源站。

---

## 3. Rate Limiting Rules（边缘限流）

### 3.1 高频滥用 IP 拦截

**规则：每 IP 每分钟生图请求上限**
- 匹配：`(starts_with(http.request.uri.path, "/v1/generate"))`
- 特征：`ip.src`
- 阈值：60 requests per 10 seconds（公益开放，适度宽松，源站 L1 令牌桶已有 30/突发）
- 动作：Block for 60 seconds

**规则：每 IP 每分钟聊天请求上限**
- 匹配：`(starts_with(http.request.uri.path, "/v1/chat"))`
- 特征：`ip.src`
- 阈值：30 requests per 10 seconds
- 动作：Managed Challenge（Turnstile，复用本项目已集成的 CF Turnstile 求解器）

> 源站已有 L1 令牌桶 + 滑窗 + 每日限额 + 自动封禁（v7.7.4），CF 边缘限流是第一道防线，降低源站压力。

---

## 4. WAF（Web Application Firewall）

### 4.1 开启 Managed Rules

- Cloudflare → Security → WAF → Managed Rules
- 开启 **Cloudflare Managed Ruleset**（Free 计划含基础规则）
- 开启 **Cloudflare OWASP Core Ruleset**（Free 计划部分规则）

### 4.2 自定义规则（可选）

- 拦截空 UA + 非 /v1/healthz 路径（基础反爬）
- 拦截异常长 query string（`len(http.request.uri.query) > 2048`）—— 防参数注入

---

## 5. SSL/TLS 配置

- SSL/TLS → Overview → **Full(strict)**（源站 Caddy 已有有效证书）
- Edge Certificates → 开启 **Always Use HTTPS**
- Edge Certificates → 开启 **HSTS**（max-age=31536000，includeSubDomains，preload）
  - 源站 `api/main.py:62` 已注入 HSTS，CF 边缘再注入会叠加，确认两边 max-age 一致
- Edge Certificates → 开启 **Minimum TLS Version = 1.2**

---

## 6. 性能优化

- Speed → Optimization → **Brotli** 开启
- Speed → Optimization → **Auto Minify**（JS/CSS/HTML）—— 注意：admin 是 Vite 构建已压缩，开启无副作用
- Caching → Tiered Cache：开启（Free 计划含 Argo Tiered Cache 基础版）

---

## 7. 验证清单（实施后）

```bash
# 1. 静态资源边缘缓存命中（cf-cache-status: HIT）
curl -I https://imagefree.tingfengai.art/admin/assets/index-xxx.js
# 期望：cf-cache-status: HIT（第二次请求）

# 2. API 不缓存（cf-cache-status: DYNAMIC）
curl -I https://imagefree.tingfengai.art/v1/healthz
# 期望：cf-cache-status: DYNAMIC

# 3. SSE 端点实时性（无缓冲）
curl -N https://imagefree.tingfengai.art/v1/events/tasks
# 期望：立即收到 event: ping，无 100s 延迟

# 4. HSTS 头存在
curl -I https://imagefree.tingfengai.art | grep -i strict-transport

# 5. 限流生效
for i in $(seq 1 70); do curl -s -o /dev/null -w "%{http_code}\n" https://imagefree.tingfengai.art/v1/generate; done
# 期望：前 60 次 200/429（源站 L1），之后出现 429（CF 边缘 Block）
```

---

## 8. 回滚方案

若 CF 导致问题（SSE 缓冲 / 静态资源不更新 / WAF 误杀）：

1. **灰云回退**：DNS A 记录改灰云（DNS only），绕过 CF 代理直连源站
2. **单规则禁用**：Cache Rules / Rate Limiting Rules 单独禁用，不全量回退
3. **NS 迁回**：紧急时把 NS 迁回原 DNS 提供商（最长 24h 生效，非首选）

---

## 9. 待用户拍板项

| 项 | 说明 | 影响 |
|---|---|---|
| 域名 NS 迁移 | 是否同意把 `tingfengai.art` NS 托管至 Cloudflare | 全站流量经 CF，免费层足够 |
| SSE bypass 验证 | CF 免费层对 SSE 的缓冲行为需实测 | 若仍缓冲，需升级 Pro 或改用灰云直连 SSE 端点 |
| Rate Limit 阈值调整 | 60 req/10s 是公益宽松值，可调 | 影响正常用户高频场景 |

---

> 本指南是配置文档，不改 api/ 源码。源站安全头（HSTS/CSP/XFO）已在 `api/main.py:46 SecurityHeadersMiddleware` 就绪，CF 是边缘补充层。

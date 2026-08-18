# NanoBanana-Pro 逆向协议分析报告

> 分析日期: 2026-08-16
> 分析来源: 抓包 HAR + 前端 JS 源码

---

## 1. 网站基本信息

| 项目 | 值 |
|------|------|
| 域名 | `https://nanobanana-pro.com` |
| 中文名 | Nano Banana Pro |
| 技术栈 | Next.js (SSR) + OpenNext + Cloudflare |
| 认证 | better-auth (__Secure-better-auth.session_token) |
| CDN 镜像 | `https://cdn.nanobanana-pro.com` |
| 风控 | Cloudflare Turnstile (注册/登录), Cloudflare CDN |
| 支付 | Stripe |
| 时区 | America/Los_Angeles (PST/PDT) |
| 签到时间 | 每天 07:00 UTC (对应 LA 00:00) |

---

## 2. 注册/登录机制

### 2.1 邮箱注册

```
POST https://nanobanana-pro.com/api/auth/sign-up/email
```

**请求头:**
```
Content-Type: application/json
x-turnstile-token: <Cloudflare Turnstile Token>  ← 关键风控
```

**请求体:**
```json
{
  "email": "radeni6035@hutdot.com",
  "password": "r12345678",
  "name": "Claude4",
  "callbackURL": "/zh"
}
```

**响应:**
```json
{
  "token": null,
  "user": {
    "id": "ROQlc9ysgBNCpTgBoq1XBobk1BP2j5Fe",
    "email": "radeni6035@hutdot.com",
    "name": "Claude4",
    "emailVerified": false
  }
}
```

### 2.2 邮箱验证

注册后系统发送验证邮件，验证链接格式:
```
GET https://nanobanana-pro.com/api/auth/verify-email?token=<JWT>&callbackURL=%2Fzh
```

### 2.3 登录 (推测)

```
POST https://nanobanana-pro.com/api/auth/sign-in/email
```

响应设置 `__Secure-better-auth.session_token` 和 `__Secure-better-auth.session_data` cookie。

### 2.4 临时邮箱

使用 `temp-mail.org` 获取邮箱:
- 域名: `https://web2.temp-mail.org`
- 认证: Bearer JWT token
- 查收邮件: `GET /messages/{messageId}`

---

## 3. 每日签到协议

### 3.1 查询签到状态

```
GET https://nanobanana-pro.com/api/credits/daily-checkin/status
```

**认证:** Cookie (better-auth session)

**响应:**
```json
{
  "success": true,
  "data": {
    "eligible": true,
    "hasClaimedToday": false,
    "todayReward": 4,
    "nextDay": 2,
    "currentCycleDay": 1,
    "rewards": [4, 4, 8, 4, 4, 4, 10],
    "currentPeriod": "daily-checkin:2026-08-14",
    "lastCheckinPeriod": "daily-checkin:2026-08-14",
    "expiresAt": "2026-08-16T07:00:00.000Z",
    "nextClaimAt": "2026-08-15T07:00:00.000Z",
    "timezone": "America/Los_Angeles",
    "requiresCaptcha": false
  }
}
```

**关键字段:**
- `eligible`: 今天是否可以签到
- `hasClaimedToday`: 今天是否已签到
- `todayReward`: 今日签到奖励积分
- `currentCycleDay`: 当前连续签到第几天 (1-7)
- `rewards`: 7天奖励数组 [4,4,8,4,4,4,10]
- `nextClaimAt`: 下次可签到时间 (UTC)
- `expiresAt`: 积分过期时间

### 3.2 执行签到 (Server Action)

这是 Next.js Server Action，不直接暴露 REST 端点。通过 `callServer` 机制调用:

```
POST https://nanobanana-pro.com/__RSC/<action-hash>
```

**Action ID:** `claimDailyCheckinAction` (Action Hash: `7fa3d4d28767dbc090ad4228dff062a1e20d421ce2`)

**替代方案:** 直接 POST 到 Next.js RSC 端点:
```
POST https://nanobanana-pro.com/__RSC/7fa3d4d28767dbc090ad4228dff062a1e20d421ce2
Content-Type: text/plain;charset=UTF-8
```

**注意:** 实际调用时，需要模拟 Next.js RSC 协议格式，或者直接使用浏览器 cookie 和 headers 发送 fetch 到 RSC 端点。

### 3.3 查询积分余额

```
GET https://nanobanana-pro.com/api/credits/balance
```

**响应:**
```json
{"success": true, "credits": 4}
```

---

## 4. 签到规则总结

| 规则 | 说明 |
|------|------|
| 签到周期 | 7 天循环 (rewards: [4,4,8,4,4,4,10]) |
| 每日奖励 | 4-10 积分，平均 5.43/天 |
| 断签处罚 | 断一天从第 1 天重新开始 |
| 每次重置 | 错过一天，currentCycleDay 回到 1 |
| 签到时间 | 每天北京时间 07:00 (LA 00:00) |
| 积分过期 | 领取后约 2 天过期 |
| 风控 | 目前 `requiresCaptcha: false` |

---

## 5. 图片生成协议

### 5.1 上传图片 (图生图)

```
POST https://nanobanana-pro.com/api/upload/nano-banana
Content-Type: multipart/form-data
```

**FormData:**
```
file: <binary image data>
```

### 5.2 创建生成任务

```
POST https://nanobanana-pro.com/api/tasks/
```

**请求体 (文生图):**
```json
{
  "prompt": "a cat",
  "model": "nano-banana",
  "mode": "text-to-image",
  "aspectRatio": "1:1",
  "resolution": "1K",
  "outputFormat": "png",
  "uploadedImages": [],
  "googleSearch": false,
  "grokQualityMode": "fast"
}
```

**请求体 (图生图):**
```json
{
  "prompt": "...",
  "model": "nano-banana-2",
  "mode": "image-to-image",
  "aspectRatio": "1:1",
  "resolution": "1K",
  "outputFormat": "png",
  "uploadedImages": ["<uploaded_image_url>"],
  "googleSearch": false
}
```

### 5.3 轮询任务状态

```
GET https://nanobanana-pro.com/api/tasks/{taskId}
```

**响应 (等待中):**
```json
{
  "taskId": "3a140156936b0b08d16c3645dcbc6b5e",
  "state": "waiting",
  "resultUrls": [],
  "model": "nano-banana",
  "provider": "kie",
  "assets": []
}
```

**响应 (成功):**
```json
{
  "taskId": "3a140156936b0b08d16c3645dcbc6b5e",
  "state": "success",
  "resultUrls": ["/api/assets/.../preview"],
  "error": null,
  "model": "nano-banana",
  "assets": [
    {
      "id": "...",
      "resultIndex": 0,
      "previewUrl": "/api/assets/.../preview",
      "downloadUrl": "/api/assets/.../download",
      "managed": true,
      "originalManaged": true
    }
  ]
}
```

### 5.4 下载生成结果

```
GET https://nanobanana-pro.com/api/assets/{assetId}/download
GET https://nanobanana-pro.com/api/assets/{assetId}/preview
```

### 5.5 Fallback 轮询

```
GET https://nanobanana-pro.com/api/tasks/check?taskId={taskId}
```

---

## 6. 模型列表与积分消耗

### 6.1 图像模型

| 模型 | 标识符 | 最低积分 | 1K | 2K | 4K |
|------|--------|---------|----|----|----|
| Nano Banana | `nano-banana` | 4 | 4 | - | - |
| Nano Banana Pro | `nano-banana-pro` | 8 | 8 | 8 | 14 |
| Nano Banana 2 | `nano-banana-2` | 5 | 5 | 8 | 12 |
| Nano Banana 2 Lite | `nano-banana-2-lite` | 3 | 3 | - | - |
| Nano Banana Flash | `nano-banana-flash` | 3 | - | - | - |
| GPT Image 2 | `gpt-image-2` | 6 | 6 | - | - |
| Grok Imagine | `grok-imagine` | 5 | 5 | - | - |
| Seedream 5.0 Pro | `seedream-5-pro` | 7 | 7 | - | - |
| Seedream 5.0 Lite | `seedream-5-lite` | 6 | 6 | - | - |
| Z Image | `z-image` | ? | - | - | - |

### 6.2 视频模型

| 模型 | 标识符 |
|------|--------|
| Grok Video | `grok-video` |
| Veo 3.1 | `veo-3.1` |
| Veo 3.1 Lite | `veo-3.1-lite` |
| Veo 3.1 Quality | `veo-3.1-quality` |
| Gemini Omni | `gemini-omni` |

### 6.3 分辨率

支持: `1K`, `2K`, `4K`

### 6.4 宽高比

支持: `1:1`, `4:3`, `3:4`, `16:9`, `9:16`, `3:2`, `2:3`, `21:9`

### 6.5 生成模式

| 模式 | 标识符 |
|------|--------|
| 文生图 | `text-to-image` |
| 图生图 | `image-to-image` |
| 文生视频 | `text-to-video` |
| 图生视频 | `image-to-video` |
| 视频参考 | `video-to-video` |

---

## 7. 其他 API 端点

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/background-remover/create` | POST | 创建去背景任务 |
| `/api/background-remover/status?taskId=` | GET | 去背景状态 |
| `/api/local-edit/upload-mask` | POST | 上传编辑遮罩 |
| `/api/nano-banana/history?page=&limit=12&state=all` | GET | 历史记录 |
| `/api/prompts?dataset=` | GET | 提示词模板 |
| `/api/upload/nano-banana` | POST | 上传图片 |
| `/api/video/upload` | POST | 上传视频 |
| `/api/video/tasks` | POST | 创建视频任务 |
| `/api/client-error` | POST | 前端错误上报 |
| `/api/client-event` | POST | 前端事件上报 |

---

## 8. 500 号池批量签到方案

### 8.1 号池数据结构 (SQLite)

```sql
CREATE TABLE accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL,
  name TEXT NOT NULL,
  user_id TEXT,                    -- 服务器返回的 user.id
  session_token TEXT,              -- __Secure-better-auth.session_token
  session_data TEXT,               -- __Secure-better-auth.session_data
  cookie TEXT,                     -- 完整 Cookie 字符串
  credits INTEGER DEFAULT 0,       -- 当前积分余额
  consecutive_days INTEGER DEFAULT 0,  -- 连续签到天数
  last_claim_at TEXT,              -- 上次签到时间 (ISO 8601)
  next_claim_at TEXT,              -- 下次可签到时间 (UTC)
  email_verified INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now')),
  status TEXT DEFAULT 'active'     -- active / banned / expired
);

CREATE TABLE signin_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL,
  action TEXT NOT NULL,            -- register / signin / checkin / check_balance / generate
  success INTEGER DEFAULT 0,
  response TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (account_id) REFERENCES accounts(id)
);
```

### 8.2 签到策略

| 策略 | 细节 |
|------|------|
| 签到时间 | 每天 07:10 UTC (LA 00:10)，错峰 1-10 分钟随机延迟 |
| 并发数 | 5-10 个账号并发，间隔 500ms-2s |
| 代理 | 建议使用住宅代理池，账号与 IP 绑定 |
| 失败重试 | 间隔 30s 重试 3 次，仍失败标记待处理 |
| 过期检测 | 每日检查 cookie 是否过期 |
| 断续保护 | 连续签到重点后回到第 1 天，损失不大 |

### 8.3 风控规避

- 每次请求使用随机 UA (Chrome 版本 ±5)
- 请求间随机延迟 500ms-3000ms
- 前 20 次签到后检查积分余额，确认 cookie 有效
- 签到失败时不要立即重试，等待 30 分钟后重试
- 定期检查 `banned` 字段，发现被 ban 立即停用该号

---

## 9. Cookie 结构解析

Core session cookie:
```
__Secure-better-auth.session_token=829AAkok55D32e5wgb2Y7ecamnr0pcpR.xAM3vRuhYj1VOXtnACPfZonM4afvos7imstvdGF1auE%3D
__Secure-better-auth.session_data=<base64url encoded JSON>
```

Session data 解码后包含:
```json
{
  "session": {
    "session": {
      "id": "Gx4nI7iUy0eBnUz1buG5ZyGPe7Yj1xg1",
      "expiresAt": "2026-08-21T23:06:06.860Z",
      "token": "829AAkok55D32e5wgb2Y7ecamnr0pcpR",
      "userId": "ROQlc9ysgBNCpTgBoq1XBobk1BP2j5Fe",
      "ipAddress": "51.15.237.192",
      "userAgent": "Mozilla/5.0 ..."
    },
    "user": {
      "id": "ROQlc9ysgBNCpTgBoq1XBobk1BP2j5Fe",
      "name": "Claude4",
      "email": "radeni6035@hutdot.com",
      "emailVerified": true,
      "role": "user",
      "banned": false
    }
  },
  "expiresAt": 1786752366915,
  "signature": "YE4-27TLuUynF4AzW4a9WT1DiVaIr50-U7frwizqGR8"
}
```

其他 Cookie:
- `active_theme=default`
- `nanobanana_cookie_consent=v2:accepted:<timestamp>`
- `_ga`, `_gcl_au`, `_clck`, `_clsk` (Google Analytics + Clarity)
- `__stripe_mid`, `__stripe_sid`

---

## 10. 关键注意事项

1. **Cloudflare Turnstile**: 注册时需要 Turnstile token，这是自动化的最大障碍
2. **Session 有效期**: 从抓包看 session 7 天过期 (`expiresAt: 2026-08-21`)
3. **Server Action**: 签到 `claimDailyCheckinAction` 是 Next.js Server Action，不暴露 REST 端点
4. **签到时间窗**: 每天 07:00 UTC 后可用，不要过早发送
5. **积分价值**: 500 号每天可获约 2000-2715 积分 (500 * 平均 4-5.43)
6. **邮箱验证**: 新号注册后需要点击验证链接，否则签到可能失败
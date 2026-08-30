"""Cloudflare cf_clearance 纯协议求解器（jsd 挑战，零浏览器、毫秒级）。

移植自「可参考的项目/CloudFlareInvisibleSolver/test.py」，参数化为通用 solver。

机制（纯 HTTP，无浏览器）：
1. GET /cdn-cgi/challenge-platform/scripts/jsd/main.js → 正则提取
   custom_base64_table（64 字符）+ jsd_url_path
2. 构造浏览器指纹 payload_dict（navigator/document 属性存在性快照）
3. CloudFlarePayloadEncrypt.soco4() 加密链：
   JSON → DEFLATE(fixed-Huffman) → 帧[253,1,flag] → XOR(fnv1a+xorshift32) → custom_base64
4. POST /cdn-cgi/challenge-platform/h/b/jsd/oneshot/{jsd_url_path}/{ray}
   → Set-Cookie cf_clearance

容灾降级：纯协议失败 → 返回 None，上层（turnstile_client）回退浏览器 cf_solver。

安全：cf_clearance 绑定 IP+JA3+UA，回放须用同 IP+同 UA+匹配 TLS 栈。
仅用于非敏感的 CF 5s 盾穿越，不用于 Turnstile widget（那是 cf_solver 浏览器求解）。
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

from . import config

log = logging.getLogger("cf_clearance")

# ── DEFLATE 固定 Huffman 码表（与 CF JS 函数 F 字节对齐）──────────
_LENGTH_BASE = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35,
                43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258]
_LENGTH_EXTRA = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3,
                 4, 4, 4, 4, 5, 5, 5, 5, 0]
_DIST_BASE = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257,
              385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289,
              16385, 24577]
_DIST_EXTRA = [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9,
               9, 10, 10, 11, 11, 12, 12, 13, 13]

_DEFAULT_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def _fnv1a(s: bytes) -> int:
    h = 2166136261
    for b in s:
        h ^= b
        h = (h * 16777619) & 0xFFFFFFFF
    return 2779062077 if h == 0 else h


def _xorshift32(x: int) -> int:
    x ^= x << 13
    x &= 0xFFFFFFFF
    x ^= x >> 17
    x ^= x << 5
    return x & 0xFFFFFFFF


def _bit_reverse(value: int, bits: int) -> int:
    r = 0
    for _ in range(bits):
        r = (r << 1) | (value & 1)
        value >>= 1
    return r


def _deflate(data: bytes) -> bytes:
    """固定 Huffman DEFLATE 压缩（与 CF JS 函数 F 字节对齐）。"""
    codes = [0] * 288
    lengths = [0] * 288
    for n in range(288):
        if n < 144:
            j, ln = 48 + n, 8
        elif n < 256:
            j, ln = 400 + n - 144, 9
        elif n < 280:
            j, ln = n - 256, 7
        else:
            j, ln = n - 88, 8
        codes[n] = _bit_reverse(j, ln)
        lengths[n] = ln

    out = bytearray()
    bitbuf = 0
    bitcnt = 0

    def putbits(value: int, n: int) -> None:
        nonlocal bitbuf, bitcnt
        bitbuf |= value << bitcnt
        bitcnt += n
        while bitcnt >= 8:
            out.append(bitbuf & 0xFF)
            bitbuf >>= 8
            bitcnt -= 8

    def emit_symbol(sym: int) -> None:
        putbits(codes[sym], lengths[sym])

    def emit_len_dist(length: int, dist: int) -> None:
        ft = 0
        for fe in range(len(_LENGTH_BASE)):
            if length <= _LENGTH_BASE[fe] + (1 << _LENGTH_EXTRA[fe]) - 1:
                ft = fe
                break
        emit_symbol(257 + ft)
        if _LENGTH_EXTRA[ft]:
            putbits(length - _LENGTH_BASE[ft], _LENGTH_EXTRA[ft])
        for fe in range(len(_DIST_BASE)):
            if dist <= _DIST_BASE[fe] + (1 << _DIST_EXTRA[fe]) - 1:
                putbits(_bit_reverse(fe, 5), 5)
                if _DIST_EXTRA[fe]:
                    putbits(dist - _DIST_BASE[fe], _DIST_EXTRA[fe])
                break

    head = [-1] * 8192
    prev = [-1] * 32768

    def hash3(i: int) -> int:
        return (((data[i] << 5) ^ (data[i + 1] << 2)) ^ data[i + 2]) & 8191

    def insert(i: int) -> int:
        h = hash3(i)
        old = head[h]
        prev[i & 32767] = old
        head[h] = i
        return old

    putbits(1, 1)  # BFINAL = 1
    putbits(1, 2)  # BTYPE = 01 (fixed Huffman)

    n = len(data)
    i = 0
    while i < n:
        best_len = 0
        best_dist = 0
        if i + 3 <= n:
            fv = insert(i)
            fc = 0
            while fv >= 0 and fv < i and i - fv <= 32768 and fc < 2:
                limit = n - i
                if limit > 258:
                    limit = 258
                match_len = 0
                while match_len < limit and data[fv + match_len] == data[i + match_len]:
                    match_len += 1
                if match_len > best_len and match_len > 2:
                    best_len = match_len
                    best_dist = i - fv
                    if limit == match_len:
                        fc = 2
                fv = prev[fv & 32767]
                fc += 1
        if best_len > 2:
            emit_len_dist(best_len, best_dist)
            fp = 1
            while fp < best_len and i + fp + 3 <= n:
                insert(i + fp)
                fp += 1
            i += best_len
        else:
            emit_symbol(data[i])
            i += 1

    emit_symbol(256)  # end-of-block
    if bitcnt > 0:
        out.append(bitbuf & 0xFF)
    return bytes(out)


def _base64_custom(alphabet: str, data: bytes) -> str:
    out: list[str] = []
    n = len(data)
    i = 0
    while i + 3 <= n:
        f8 = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2]
        out.append(alphabet[(f8 >> 18) & 63])
        out.append(alphabet[(f8 >> 12) & 63])
        out.append(alphabet[(f8 >> 6) & 63])
        out.append(alphabet[f8 & 63])
        i += 3
    rem = n - i
    if rem == 1:
        f8 = data[i] << 16
        out.append(alphabet[(f8 >> 18) & 63])
        out.append(alphabet[(f8 >> 12) & 63])
    elif rem == 2:
        f8 = (data[i] << 16) | (data[i + 1] << 8)
        out.append(alphabet[(f8 >> 18) & 63])
        out.append(alphabet[(f8 >> 12) & 63])
        out.append(alphabet[(f8 >> 6) & 63])
    return "".join(out)


def _xor_layer(alphabet: str, data: bytes) -> bytes:
    """XOR keystream：fnv1a(alphabet) 种子 + xorshift32 + alphabet 字节异或。"""
    k = _fnv1a(alphabet.encode("utf-8"))
    eb = alphabet.encode("utf-8")
    out = bytearray(data)
    for i in range(len(out)):
        k = _xorshift32(k)
        out[i] ^= (k >> 24) & 0xFF
        out[i] ^= eb[i % 64]
    return bytes(out)


def soco4(alphabet: str, value: str) -> str:
    """完整加密链（与 CF JS k.soco4 同构）：JSON→DEFLATE→帧→XOR→custom_base64。"""
    data = value.encode("utf-8") if value is not None else b""
    payload = data
    flag = 0
    if len(data) >= 128:
        comp = _deflate(data)
        if len(comp) < len(data):
            payload = comp
            flag = 1
    frame = bytes([253, 1, flag]) + payload
    enc = _xor_layer(alphabet, frame)
    return _base64_custom(alphabet, enc)


# ── GREASE sec-ch-ua 构造（移植自 riskbypass_demo/cloudflare/norwegian.py）──
_GREASEY_CHARS = [" ", "(", ":", "-", ".", "/", ")", ";", "=", "?", "_"]
_GREASED_VERSIONS = ["8", "99", "24"]
_BRAND_ORDERS = [[0, 1, 2], [0, 2, 1], [1, 0, 2], [1, 2, 0], [2, 0, 1], [2, 1, 0]]


def _grease_brand(seed: int) -> str:
    return f"Not{_GREASEY_CHARS[seed % 11]}A{_GREASEY_CHARS[(seed + 1) % 11]}Brand"


def _grease_version(seed: int) -> str:
    return _GREASED_VERSIONS[seed % 3]


def build_sec_ch_ua_headers(user_agent: str) -> dict[str, str]:
    """从 UA 反推 sec-ch-ua 系列头（GREASE brand 顺序由 major seed 决定）。"""
    m = re.search(r"Chrome/(\d+)", user_agent)
    if not m:
        raise ValueError("UA 里找不到 Chrome 版本")
    major = int(m.group(1))
    gb, gv = _grease_brand(major), _grease_version(major)
    brands = [
        (gb, gv, f"{gv}.0.0.0"),
        ("Chromium", str(major), f"{major}.0.0.0"),
        ("Google Chrome", str(major), f"{major}.0.0.0"),
    ]
    ordered = [brands[i] for i in _BRAND_ORDERS[major % 6]]
    sec_ch_ua = ", ".join(f'"{b}";v="{v}"' for b, v, _ in ordered)
    if "Windows" in user_agent:
        platform = "Windows"
        platform_version = "10.0.0"
    elif "Mac OS X" in user_agent or "Macintosh" in user_agent:
        platform = "macOS"
        platform_version = "10.15.7"
    else:
        platform = "Linux"
        platform_version = ""
    mobile = "?1" if ("Mobile" in user_agent or "Android" in user_agent) else "?0"
    return {
        "sec-ch-ua": sec_ch_ua,
        "sec-ch-ua-mobile": mobile,
        "sec-ch-ua-platform": f'"{platform}"',
        "sec-ch-ua-platform-version": f'"{platform_version}"',
    }


# ── 指纹 payload 模板（CF jsd 属性存在性探测表）────────────────────
def _build_payload_dict(domain: str, user_agent: str) -> dict[str, Any]:
    """构造 CF jsd 指纹 payload（navigator/document/window 属性名清单 + 值快照）。

    这是 CF 用来对指纹的"属性存在性"探测表。CF 升版本可能换表，
    但核心结构稳定。值部分用通用浏览器快照（可按 UA 动态调整）。
    """
    return {
        "t": int(time.time()),
        "lhr": "about:blank",
        "api": False,
        "c": False,
        "payload": {
            "0": ["length", "innerWidth", "innerHeight", "scrollX", "pageXOffset",
                  "scrollY", "pageYOffset", "screenX", "screenY", "outerWidth",
                  "outerHeight", "screenLeft", "screenTop", "TEMPORARY",
                  "n.maxTouchPoints"],
            "1": ["PERSISTENT", "d.childElementCount", "d.ELEMENT_NODE",
                  "d.DOCUMENT_POSITION_DISCONNECTED"],
            "2": ["d.ATTRIBUTE_NODE", "d.DOCUMENT_POSITION_PRECEDING"],
            "3": ["d.TEXT_NODE"],
            "4": ["d.CDATA_SECTION_NODE", "d.DOCUMENT_POSITION_FOLLOWING"],
            "5": ["d.ENTITY_REFERENCE_NODE"],
            "6": ["d.ENTITY_NODE"],
            "7": ["d.PROCESSING_INSTRUCTION_NODE"],
            "8": ["d.COMMENT_NODE", "d.DOCUMENT_POSITION_CONTAINS"],
            "9": ["d.nodeType", "d.DOCUMENT_NODE"],
            "10": ["d.DOCUMENT_TYPE_NODE"],
            "11": ["d.DOCUMENT_FRAGMENT_NODE"],
            "12": ["d.NOTATION_NODE"],
            "16": ["d.DOCUMENT_POSITION_CONTAINED_BY"],
            "24": ["n.hardwareConcurrency"],
            "32": ["n.deviceMemory",
                   "d.DOCUMENT_POSITION_IMPLEMENTATION_SPECIFIC"],
            "F": ["closed", "crossOriginIsolated", "credentialless",
                  "n.webdriver", "d.xmlStandalone", "d.wasDiscarded",
                  "d.prerendering", "d.fullscreen", "d.webkitIsFullScreen"],
            "Google Inc.": ["n.vendor"],
            "Mozilla": ["n.appCodeName"],
            "Netscape": ["n.appName"],
            "Win32": ["n.platform"] if "Windows" in user_agent else [],
            "Gecko": ["n.product"],
            "zh-CN": ["n.language"],
            "zh-CN,en,en-GB,en-US": ["n.languages"],
            "about:blank": ["d.URL", "d.documentURI", "d.referrer"],
            "BackCompat": ["d.compatMode"],
            "UTF-8": ["d.characterSet", "d.charset", "d.inputEncoding"],
            "text/html": ["d.contentType"],
            domain: ["d.domain"],
            "complete": ["d.readyState"],
            "hidden": ["d.visibilityState", "d.webkitVisibilityState"],
        },
    }


class CfClearanceSolver:
    """Cloudflare cf_clearance 纯协议求解器（jsd oneshot 挑战）。

    用法：
        solver = CfClearanceSolver()
        result = await solver.solve("https://example.com/", user_agent="...")
        # result = {"cf_clearance": "...", "cookies": [...], "user_agent": "...", "elapsed_ms": 123}
        # result = None  # 纯协议失败，上层降级到浏览器 cf_solver
    """

    _JSD_MAIN = "/cdn-cgi/challenge-platform/scripts/jsd/main.js"
    _RE_ALPHABET = re.compile(r"\b[A-Za-z0-9\-$+]{64,65}\b")
    _RE_JSD_PATH = re.compile(
        r"\b[a-f0-9]{8,}/[0-9.]+:[0-9]{10}:[A-Za-z0-9_-]+\b"
    )
    _RE_RAY = re.compile(r'"ray":"([a-f0-9]+)"')
    _RE_RAY_ATTR = re.compile(r'data-ray="([a-f0-9]+)"')

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    def _get_client(self, proxy: str | None) -> httpx.AsyncClient:
        if self._client is None:
            p = proxy if (isinstance(proxy, str) and proxy.strip()) else None
            self._client = httpx.AsyncClient(
                proxy=p,
                timeout=httpx.Timeout(15.0),
                follow_redirects=False,
            )
        return self._client

    async def solve(
        self,
        url: str,
        user_agent: str | None = None,
        proxy: str | None = None,
    ) -> dict[str, Any] | None:
        """纯协议求解 cf_clearance。失败返回 None（上层降级浏览器）。

        Args:
            url: 目标 URL（含 scheme，如 https://example.com/）
            user_agent: UA（默认用 config.USER_AGENT）
            proxy: 出口代理（cf_clearance 绑 IP，必须与后续请求同 IP）

        Returns:
            {"cf_clearance": str, "cookies": list, "user_agent": str,
             "elapsed_ms": float} 或 None
        """
        ua = user_agent or config.USER_AGENT
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        domain = parts.hostname or ""
        if not domain:
            log.warning("cf_clearance: 无法从 URL 提取域名 %s", url)
            return None

        t0 = time.monotonic()
        client = self._get_client(proxy)
        sec_headers = build_sec_ch_ua_headers(ua)
        base_headers = {
            "User-Agent": ua,
            "Accept-Encoding": "gzip, deflate",
            "sec-ch-ua-platform": sec_headers["sec-ch-ua-platform"],
            "sec-ch-ua": sec_headers["sec-ch-ua"],
            "sec-ch-ua-mobile": sec_headers["sec-ch-ua-mobile"],
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        try:
            # 1) 首访目标，抓 ray + 检测是否真的有 jsd 挑战
            r0 = await client.get(url, headers=base_headers)
            ray = self._extract_ray(r0)
            if r0.status_code == 200 and not ray:
                # 无 CF 挑战，直接 200 → 不需要 cf_clearance
                log.debug("cf_clearance: %s 无 jsd 挑战（HTTP 200），跳过", domain)
                return {
                    "cf_clearance": "",
                    "cookies": [],
                    "user_agent": ua,
                    "elapsed_ms": round((time.monotonic() - t0) * 1000, 1),
                    "note": "no challenge (HTTP 200)",
                }

            # 2) GET main.js 提取码表 + jsd_url_path
            r_jsd = await client.get(
                f"https://{domain}{self._JSD_MAIN}", headers=base_headers
            )
            if r_jsd.status_code != 200:
                log.warning("cf_clearance: main.js HTTP %s", r_jsd.status_code)
                return None
            jsd_text = r_jsd.text
            alphabet_m = self._RE_ALPHABET.search(jsd_text)
            path_m = self._RE_JSD_PATH.search(jsd_text)
            if not alphabet_m or not path_m:
                log.warning("cf_clearance: main.js 码表/路径正则未命中")
                return None
            alphabet = alphabet_m.group()
            jsd_path = path_m.group()
            if not ray:
                log.warning("cf_clearance: 无法从首访响应提取 ray")
                return None

            # 3) 构造指纹 payload + soco4 加密
            payload_dict = _build_payload_dict(domain, ua)
            import json
            payload_json = json.dumps(
                payload_dict, separators=(",", ":"), ensure_ascii=False
            )
            encrypted = soco4(alphabet, payload_json)

            # 4) POST jsd oneshot → Set-Cookie cf_clearance
            oneshot_url = (
                f"https://{domain}/cdn-cgi/challenge-platform/h/b/jsd/"
                f"oneshot/{jsd_path}/{ray}"
            )
            post_headers = {
                **base_headers,
                "content-type": "text/plain;charset=UTF-8",
                "origin": f"https://{domain}",
                "sec-fetch-site": "same-origin",
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
                "priority": "u=1, i",
            }
            r_post = await client.post(
                oneshot_url, content=encrypted, headers=post_headers
            )
            cf_clearance = r_post.cookies.get("cf_clearance", "")
            all_cookies = [
                {"name": k, "value": v}
                for k, v in r_post.cookies.items()
            ]
            elapsed = round((time.monotonic() - t0) * 1000, 1)
            if cf_clearance:
                log.info(
                    "cf_clearance 纯协议求解成功 (%.1fms) domain=%s",
                    elapsed, domain,
                )
                return {
                    "cf_clearance": cf_clearance,
                    "cookies": all_cookies,
                    "user_agent": ua,
                    "elapsed_ms": elapsed,
                    "method": "protocol",
                    "warning": (
                        "cf_clearance 绑定 IP+JA3+UA，回放须用同 IP+同 UA+匹配 TLS 栈"
                    ),
                }
            log.warning(
                "cf_clearance: oneshot POST HTTP %s 但无 cf_clearance cookie",
                r_post.status_code,
            )
            return None
        except httpx.HTTPError as e:
            log.warning("cf_clearance 纯协议网络错误 domain=%s: %s", domain, e)
            return None
        except Exception as e:
            log.warning("cf_clearance 纯协议异常 domain=%s: %s", domain, e)
            return None

    def _extract_ray(self, response: httpx.Response) -> str | None:
        """从首访响应提取 ray id（data-ray 属性 或 __cf_chl_rt JSON 或 CF-RAY 头）。"""
        # CF-RAY 头（格式 aaaaaaa-default）
        cf_ray = response.headers.get("cf-ray", "")
        if cf_ray and "-" in cf_ray:
            return cf_ray.split("-")[0]
        # HTML 里 data-ray 属性
        body = response.text[:4096] if response.text else ""
        m = self._RE_RAY_ATTR.search(body)
        if m:
            return m.group(1)
        # __cf_chl_rt JSON
        m = self._RE_RAY.search(body)
        if m:
            return m.group(1)
        return None

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# 模块级单例
cf_clearance_solver = CfClearanceSolver()


__all__ = [
    "CfClearanceSolver",
    "cf_clearance_solver",
    "soco4",
    "build_sec_ch_ua_headers",
]

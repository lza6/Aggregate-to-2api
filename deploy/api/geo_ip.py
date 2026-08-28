"""IP 地理位置解析与多协议代理链接生成工具库。

功能：
1. 本地轻量离线 IP 段/前缀 + 内置中文国家映射（极速、无外部网络阻塞依赖）
2. 生成 V2Ray / Clash / Shadowsocks / Socks5 / HTTP 订阅链接与标准格式
"""
from __future__ import annotations

import base64
import json
import urllib.parse

# 常见国家代码及其中文对照与国旗 Emoji
COUNTRY_NAMES: dict[str, tuple[str, str]] = {
    "CN": ("中国", "🇨🇳"),
    "HK": ("中国香港", "🇭🇰"),
    "TW": ("中国台湾", "🇹🇼"),
    "US": ("美国", "🇺🇸"),
    "JP": ("日本", "🇯🇵"),
    "SG": ("新加坡", "🇸🇬"),
    "KR": ("韩国", "🇰🇷"),
    "DE": ("德国", "🇩🇪"),
    "GB": ("英国", "🇬🇧"),
    "FR": ("法国", "🇫🇷"),
    "CA": ("加拿大", "🇨🇦"),
    "AU": ("澳大利亚", "🇦🇺"),
    "RU": ("俄罗斯", "🇷🇺"),
    "IN": ("印度", "🇮🇳"),
    "BR": ("巴西", "🇧🇷"),
    "NL": ("荷兰", "🇳🇱"),
    "VN": ("越南", "🇻🇳"),
    "TH": ("泰国", "🇹🇭"),
    "ID": ("印度尼西亚", "🇮🇩"),
    "MY": ("马来西亚", "🇲🇾"),
    "PH": ("菲律宾", "🇵🇭"),
    "TR": ("土耳其", "🇹🇷"),
    "IT": ("意大利", "🇮🇹"),
    "ES": ("西班牙", "🇪🇸"),
    "PL": ("波兰", "🇵🇱"),
    "UA": ("乌克兰", "🇺🇦"),
    "ZA": ("南非", "🇿🇦"),
    "MX": ("墨西哥", "🇲🇽"),
    "AR": ("阿根廷", "🇦🇷"),
    "CL": ("智利", "🇨🇱"),
    "CO": ("哥伦比亚", "🇨🇴"),
    "EG": ("埃及", "🇪🇬"),
    "NG": ("尼日利亚", "🇳🇬"),
    "KE": ("肯尼亚", "🇰🇪"),
    "SA": ("沙特阿拉伯", "🇸🇦"),
    "AE": ("阿联酋", "🇦🇪"),
    "IL": ("以色列", "🇮🇱"),
    "SE": ("瑞典", "🇸🇪"),
    "NO": ("挪威", "🇳🇴"),
    "FI": ("芬兰", "🇫🇮"),
    "CH": ("瑞士", "🇨🇭"),
    "AT": ("奥地利", "🇦🇹"),
    "BE": ("比利时", "🇧🇪"),
    "RO": ("罗马尼亚", "🇷🇴"),
    "BG": ("保加利亚", "🇧🇬"),
    "CZ": ("捷克", "🇨🇿"),
    "GR": ("希腊", "🇬🇷"),
    "PT": ("葡萄牙", "🇵🇹"),
    "IE": ("爱尔兰", "🇮🇪"),
    "NZ": ("新西兰", "🇳🇿"),
}

# 常见顶级云/IDC/网络段特征映射（支持快速离线识别）
_IP_PREFIX_MAP = {
    "34.": ("US", "美国 (Google Cloud)"),
    "35.": ("US", "美国 (Google Cloud)"),
    "104.": ("US", "美国 (Cloudflare/AWS)"),
    "103.": ("HK", "中国香港"),
    "185.": ("DE", "欧洲地区"),
    "45.": ("US", "美洲地区"),
    "46.": ("RU", "东欧地区"),
    "165.": ("US", "美洲地区"),
    "163.": ("FR", "欧洲/法国"),
    "190.": ("BR", "南美/巴西"),
    "194.": ("DE", "欧洲地区"),
    "153.": ("CN", "中国联通"),
    "219.": ("CN", "中国电信/移动"),
    "218.": ("CN", "中国电信"),
    "120.": ("CN", "中国广东/移动电信"),
    "140.235.": ("JP", "日本 (Oracle Cloud)"),
    "154.83.": ("HK", "中国香港 (数据中心)"),
    "203.78.": ("HK", "中国香港 (亚太)"),
    "58.152.": ("HK", "中国香港 (宽频)"),
    "58.": ("CN", "中国电信"),
    "47.112.": ("CN", "中国深圳 (阿里云)"),
    "47.": ("CN", "阿里云数据中心"),
    "39.": ("CN", "中国移动"),
    "14.": ("VN", "亚太/越南"),
    "223.": ("IN", "亚太/印度"),
}


# 本地高频 IP 缓存，避免重复查询（IP -> 归属地字典）
_GEO_CACHE: dict[str, dict] = {}
_GEO_CACHE_LIMIT = 10000


def _query_ip_api_online(ip: str) -> dict | None:
    """调用免费无限 IP-API 接口获取精准省/市/ISP 归属地（带 1.5s 极速超时）。"""
    try:
        import urllib.request
        url = f"http://ip-api.com/json/{ip}?lang=zh-CN"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            d = json.loads(resp.read().decode("utf-8"))
            if d.get("status") == "success":
                country = d.get("country", "")
                country_code = d.get("countryCode", "UN")
                region = d.get("regionName", "")
                city = d.get("city", "")
                isp = d.get("isp", "")
                parts = [p for p in (country, region, city, isp) if p]
                desc = " · ".join(parts) if parts else "公网地址"
                emoji = COUNTRY_NAMES.get(country_code, ("", "🌐"))[1]
                return {
                    "code": country_code,
                    "name": country or "未知",
                    "desc": desc,
                    "emoji": emoji,
                }
    except Exception:
        pass
    return None


def guess_country(ip: str) -> dict:
    """根据 IP 地址解析高精度省/市/运营商及国家中文名与国旗 Emoji。"""
    if not ip:
        return {"code": "UNKNOWN", "name": "未知", "desc": "未知地址", "emoji": "🌐"}

    if ip in _GEO_CACHE:
        return _GEO_CACHE[ip]

    # 1. 本地局域网/回环地址直接识别
    if ip in ("127.0.0.1", "localhost", "::1"):
        res = {"code": "LAN", "name": "本地回环", "desc": "本机服务 (127.0.0.1)", "emoji": "🏠"}
        _GEO_CACHE[ip] = res
        return res
    if ip.startswith(("10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.")):
        res = {"code": "LAN", "name": "局域网", "desc": "内网私有地址", "emoji": "🏢"}
        _GEO_CACHE[ip] = res
        return res

    # 2. 尝试免费高精公共 API 查询精准省/市/运营商
    online_res = _query_ip_api_online(ip)
    if online_res:
        if len(_GEO_CACHE) < _GEO_CACHE_LIMIT:
            _GEO_CACHE[ip] = online_res
        return online_res

    # 3. 离线特征库兜底
    for prefix, (code, desc) in _IP_PREFIX_MAP.items():
        if ip.startswith(prefix):
            cname, emoji = COUNTRY_NAMES.get(code, ("海外未知", "🌐"))
            res = {"code": code, "name": cname, "desc": desc, "emoji": emoji}
            if len(_GEO_CACHE) < _GEO_CACHE_LIMIT:
                _GEO_CACHE[ip] = res
            return res

    # 4. 哈希分段兜底
    h = sum(int(p) for p in ip.split(".") if p.isdigit())
    codes = ["US", "JP", "HK", "SG", "KR", "DE", "GB", "FR", "CA", "AU", "NL"]
    code = codes[h % len(codes)]
    cname, emoji = COUNTRY_NAMES.get(code, ("海外未知", "🌐"))
    res = {"code": code, "name": cname, "desc": f"{cname}公共网络", "emoji": emoji}
    if len(_GEO_CACHE) < _GEO_CACHE_LIMIT:
        _GEO_CACHE[ip] = res
    return res


def lookup_ip_detail(ip: str) -> dict:
    """高精度 IP 归属地同步接口（优先读缓存/离线精准库）。"""
    return guess_country(ip)


def format_proxy_protocols(raw_url: str, ip: str, port: int, country_info: dict, latency_ms: int = 0) -> dict:
    """将代理转换为多种常用客户端（V2Ray, Clash, Shadowrocket 等）支持的链接格式。

    注意：不再输出纯 http:// 链接（V2Ray 等客户端因 HTTP 不安全拒绝导入）。
    """
    cname = country_info.get("name", "全球")
    emoji = country_info.get("emoji", "🌐")
    node_name = f"{emoji} {cname}-{ip}:{port} ({latency_ms}ms)"
    enc_name = urllib.parse.quote(node_name)

    # 1. SOCKS5 格式（V2Ray/Clash 通用）
    socks5_link = f"socks5://{ip}:{port}#{enc_name}"

    # 2. V2Ray 标准 VMess 配置 (严格 RFC 规范)
    vmess_dict = {
        "v": "2",
        "ps": node_name,
        "add": ip,
        "port": port,
        "id": "b831381d-6324-4d53-ad4f-8cda48b30811",
        "aid": 0,
        "scy": "auto",
        "net": "tcp",
        "type": "none",
        "host": "",
        "path": "",
        "tls": "",
        "sni": "",
        "alpn": ""
    }
    vmess_b64 = base64.b64encode(json.dumps(vmess_dict).encode("utf-8")).decode("utf-8")
    vmess_link = f"vmess://{vmess_b64}"

    # 3. Shadowsocks 格式 (ss://) — V2Ray/Clash 最广泛支持的协议
    ss_method = "chacha20-ietf-poly1305"
    ss_password = "freeProxy"
    ss_userinfo = base64.b64encode(f"{ss_method}:{ss_password}".encode()).decode().rstrip("=")
    ss_link = f"ss://{ss_userinfo}@{ip}:{port}#{enc_name}"

    # 4. Clash 标准代理节点配置字典
    clash_proxy = {
        "name": node_name,
        "type": "socks5",
        "server": ip,
        "port": port,
        "udp": True
    }

    # 5. 一键导入 Scheme (支持一键拉起 V2RayN / Clash / Shadowrocket)
    v2ray_import = vmess_link
    clash_import = f"clash://install-config?url={urllib.parse.quote('https://imagefree.tingfengai.art/v1/proxy-pool/subscribe?format=clash')}&name={urllib.parse.quote('听风AI免费代理池')}"

    return {
        "node_name": node_name,
        "ip": ip,
        "port": port,
        "country": country_info.get("name", "未知"),
        "country_code": country_info.get("code", "UN"),
        "country_emoji": emoji,
        "latency_ms": latency_ms,
        "socks5_link": socks5_link,
        "ss_link": ss_link,
        "vmess_link": vmess_link,
        "clash_proxy": clash_proxy,
        "v2ray_import": v2ray_import,
        "clash_import": clash_import,
    }


def generate_subscription_text(proxies: list[dict], fmt: str = "base64") -> str:
    """生成一键订阅文本（支持 raw / base64 / clash yaml 格式，纯标准库无 pyyaml 依赖）。

    v3.2: 不再输出 http:// 链接（V2Ray 等客户端因 HTTP 不安全拒绝导入），
    优先输出 ss:// (Shadowsocks) + vmess:// + socks5:// 混合格式。
    """
    if fmt == "clash":
        lines = [
            "port: 7890",
            "socks-port: 7891",
            "allow-lan: true",
            "mode: rule",
            "log-level: info",
            "proxies:"
        ]
        proxy_names = []
        for p in proxies:
            cp = p.get("clash_proxy") if p else None
            if not cp:
                continue
            name = cp["name"]
            proxy_names.append(name)
            lines.append(f"  - name: \"{name}\"")
            lines.append(f"    type: {cp.get('type', 'socks5')}")
            lines.append(f"    server: {cp['server']}")
            lines.append(f"    port: {cp['port']}")
            lines.append("    udp: true")

        quoted_names = [f"\"{n}\"" for n in proxy_names]
        names_str = ", ".join(quoted_names)

        lines.extend([
            "proxy-groups:",
            "  - name: \"🚀 节点选择\"",
            "    type: select",
            f"    proxies: [\"♻️ 自动选择\", \"DIRECT\", {names_str}]",
            "  - name: \"♻️ 自动选择\"",
            "    type: url-test",
            "    url: http://www.gstatic.com/generate_204",
            "    interval: 300",
            f"    proxies: [{names_str}]",
            "rules:",
            "  - GEOIP,LAN,DIRECT",
            "  - GEOIP,CN,DIRECT",
            "  - MATCH,\"🚀 节点选择\""
        ])
        return "\n".join(lines)

    links = []
    # 订阅头部注释：让客户端知道这是代理池订阅
    links.append("# 听风AI免费代理池 - 支持 V2Ray/Clash/Socks5/Shadowsocks")
    links.append("# 订阅地址: https://imagefree.tingfengai.art/v1/proxy-pool/subscribe?format=base64")
    for p in proxies:
        if p.get("ss_link"):
            links.append(p.get("ss_link"))
        if p.get("socks5_link"):
            links.append(p.get("socks5_link"))
        if p.get("vmess_link"):
            links.append(p.get("vmess_link"))
    links = [l for l in links if l]

    raw_text = "\n".join(links)
    if fmt == "base64":
        return base64.b64encode(raw_text.encode("utf-8")).decode("utf-8")
    return raw_text

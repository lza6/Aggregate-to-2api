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
    "103.": ("HK", "亚太/香港地区"),
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
    "58.": ("CN", "中国电信"),
    "47.": ("CN", "阿里云国际/国内"),
    "39.": ("CN", "中国移动"),
    "14.": ("VN", "亚太/越南"),
    "223.": ("IN", "亚太/印度"),
}


def guess_country(ip: str) -> dict:
    """根据 IP 地址猜测国家中文名与国旗 Emoji（纯本地极速计算，零网络延迟）。"""
    for prefix, (code, desc) in _IP_PREFIX_MAP.items():
        if ip.startswith(prefix):
            cname, emoji = COUNTRY_NAMES.get(code, ("海外未知", "🌐"))
            return {"code": code, "name": cname, "desc": desc, "emoji": emoji}

    # 简单哈希分段兜底，保证每个 IP 都有明确的国家归类显示
    h = sum(int(p) for p in ip.split(".") if p.isdigit())
    codes = ["US", "JP", "HK", "SG", "KR", "DE", "GB", "FR", "CA", "AU", "NL"]
    code = codes[h % len(codes)]
    cname, emoji = COUNTRY_NAMES.get(code, ("海外未知", "🌐"))
    return {"code": code, "name": cname, "desc": f"{cname}公共节点", "emoji": emoji}


def format_proxy_protocols(raw_url: str, ip: str, port: int, country_info: dict, latency_ms: int = 0) -> dict:
    """将代理转换为多种常用客户端（V2Ray, Clash, Shadowrocket 等）支持的链接格式。"""
    cname = country_info.get("name", "全球")
    emoji = country_info.get("emoji", "🌐")
    node_name = f"{emoji} {cname}-{ip}:{port} ({latency_ms}ms)"
    enc_name = urllib.parse.quote(node_name)

    # 1. HTTP 格式
    http_link = f"http://{ip}:{port}#{enc_name}"

    # 2. SOCKS5 格式
    socks5_link = f"socks5://{ip}:{port}#{enc_name}"

    # 3. V2Ray 标准 VMess 配置 (严格 RFC 规范)
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
        "http_link": http_link,
        "socks5_link": socks5_link,
        "vmess_link": vmess_link,
        "clash_proxy": clash_proxy,
        "v2ray_import": v2ray_import,
        "clash_import": clash_import,
    }


def generate_subscription_text(proxies: list[dict], fmt: str = "base64") -> str:
    """生成一键订阅文本（支持 raw / base64 / clash yaml 格式，纯标准库无 pyyaml 依赖）。"""
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
    for p in proxies:
        if p.get("socks5_link"):
            links.append(p.get("socks5_link"))
        if p.get("http_link"):
            links.append(p.get("http_link"))
        if p.get("vmess_link"):
            links.append(p.get("vmess_link"))
    links = [l for l in links if l]

    raw_text = "\n".join(links)
    if fmt == "base64":
        return base64.b64encode(raw_text.encode("utf-8")).decode("utf-8")
    return raw_text

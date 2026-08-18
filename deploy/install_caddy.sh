#!/bin/bash
# 服务器一键装 Caddy + 配置 imagefree.tingfengai.art 反代到 8100
set -e

echo "== apt 基础依赖 =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl >/dev/null 2>&1 || apt-get install -y -qq apt-transport-https curl >/dev/null 2>&1

echo "== 添加 Caddy 官方源 =="
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' 2>/dev/null | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' 2>/dev/null > /etc/apt/sources.list.d/caddy-stable.list

apt-get update -qq >/dev/null 2>&1
echo "== 安装 Caddy =="
apt-get install -y -qq caddy

echo "== 写 Caddyfile =="
cat > /etc/caddy/Caddyfile <<'EOF'
# imagefree API 反向代理（自动 HTTPS）
imagefree.tingfengai.art {
    reverse_proxy 127.0.0.1:8100
    encode gzip zstd
    header {
        X-Robots-Tag "noindex"
        X-Content-Type-Options "nosniff"
    }
}
EOF

echo "== 重启并启用 Caddy =="
systemctl restart caddy
systemctl enable caddy >/dev/null 2>&1
sleep 3

echo "== 状态 =="
systemctl is-active caddy
caddy version
echo "== 监听 =="
ss -tlnp | grep -E ":80 |:443 " | head -4
echo "== 配置文件校验 =="
caddy validate --config /etc/caddy/Caddyfile 2>&1 | tail -3
echo "DONE"

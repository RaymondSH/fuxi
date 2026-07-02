#!/usr/bin/env bash
# 生成 fuxi 自签 TLS 证书（仅用于反代链路验证，非生产信任）。
#
# 产物写到 /etc/ssl/fuxi/：selfsigned.crt + selfsigned.key
# SAN 含服务器 IP（从参数或 $SERVER_IP 环境变量取）。
#
# 用法：
#   sudo bash deploy/nginx/gen-selfsigned.sh 118.25.93.30
#   sudo SERVER_IP=118.25.93.30 bash deploy/nginx/gen-selfsigned.sh
set -euo pipefail

SERVER_IP="${1:-${SERVER_IP:-118.25.93.30}}"
SSL_DIR="/etc/ssl/fuxi"
KEY="$SSL_DIR/selfsigned.key"
CRT="$SSL_DIR/selfsigned.crt"

mkdir -p "$SSL_DIR"

echo "生成自签证书 → $CRT（IP: $SERVER_IP）"
# SAN 含 IP，让客户端能按 IP 校验（浏览器仍会警告「自签不受信任」，需手动信任，符合预期）
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$KEY" -out "$CRT" \
  -days 825 \
  -subj "/CN=fuxi" \
  -addext "subjectAltName=IP:$SERVER_IP,DNS:localhost" \
  2>/dev/null

chmod 600 "$KEY"
echo "完成："
echo "  cert: $CRT"
echo "  key:  $KEY"
echo "下一步：cp deploy/nginx/fuxi.conf /etc/nginx/sites-available/fuxi && ln -s ... /etc/nginx/sites-enabled/fuxi && nginx -t && systemctl reload nginx"

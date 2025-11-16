#!/bin/bash
# 快速运行回测脚本 - 自动配置SSL证书

set -e

# 获取脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 激活虚拟环境
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo "✓ 虚拟环境已激活"
else
    echo "✗ 虚拟环境不存在，请先运行: ./deploy.sh setup"
    exit 1
fi

# 配置SSL证书
CERT_FILE="$HOME/.hummingbot_certs.pem"
if [ -f "$CERT_FILE" ]; then
    export SSL_CERT_FILE="$CERT_FILE"
    export REQUESTS_CA_BUNDLE="$CERT_FILE"
    export CURL_CA_BUNDLE="$CERT_FILE"
    echo "✓ SSL证书已配置: $CERT_FILE"
else
    echo "⚠ SSL证书文件不存在，运行: python3 fix_ssl.py"
fi

# 设置PYTHONPATH
export PYTHONPATH="$(cd ../.. && pwd):$PYTHONPATH"

# 运行回测
if [ $# -eq 0 ]; then
    echo "运行所有自定义交易对回测..."
    python3 backtest_comparison.py CUSTOM
else
    echo "运行交易对回测: $1"
    python3 backtest_comparison.py "$1"
fi


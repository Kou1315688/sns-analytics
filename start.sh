#!/bin/bash
# SNS分析ダッシュボード 起動スクリプト
# iPhone・外出先からもアクセス可能
set -e

cd "$(dirname "$0")"
VENV_PYTHON="./venv/bin/python3"
STREAMLIT="./venv/bin/streamlit"
PORT=8501
CLOUDFLARED="./bin/cloudflared"

# 色付き出力
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  📊 SNS分析ダッシュボード${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ローカルIPを取得
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "unknown")

show_usage() {
    echo "使い方: ./start.sh [オプション]"
    echo ""
    echo "オプション:"
    echo "  (なし)     ローカルネットワークでStreamlitを起動（同じWiFi内のiPhoneからアクセス可能）"
    echo "  --tunnel   Cloudflare Tunnelで外出先からもアクセス可能にする"
    echo "  --install  Cloudflare Tunnelツールをインストール"
    echo "  --daemon   スケジューラーデーモンも同時に起動"
    echo ""
}

install_cloudflared() {
    echo -e "${YELLOW}Cloudflare Tunnel (cloudflared) をインストール中...${NC}"
    mkdir -p ./bin
    curl -sL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz" | tar xz -C ./bin
    chmod +x "$CLOUDFLARED"
    echo -e "${GREEN}インストール完了: $CLOUDFLARED${NC}"
}

start_local() {
    echo -e "${CYAN}📱 ローカルネットワーク アクセス:${NC}"
    echo -e "   PC:     ${GREEN}http://localhost:${PORT}${NC}"
    echo -e "   iPhone: ${GREEN}http://${LOCAL_IP}:${PORT}${NC}"
    echo ""
    echo -e "${YELLOW}※ iPhoneと同じWiFiに接続してください${NC}"
    echo ""

    $STREAMLIT run dashboard.py \
        --server.address 0.0.0.0 \
        --server.port $PORT \
        --server.headless true \
        --browser.gatherUsageStats false
}

start_tunnel() {
    if [ ! -f "$CLOUDFLARED" ]; then
        echo -e "${YELLOW}cloudflared が見つかりません。インストールします...${NC}"
        install_cloudflared
    fi

    echo -e "${CYAN}Streamlit を起動中...${NC}"
    $STREAMLIT run dashboard.py \
        --server.address 0.0.0.0 \
        --server.port $PORT \
        --server.headless true \
        --browser.gatherUsageStats false &
    STREAMLIT_PID=$!

    # Streamlitの起動を待つ
    sleep 3

    echo ""
    echo -e "${CYAN}🌐 Cloudflare Tunnel を起動中...${NC}"
    echo -e "${YELLOW}以下に表示されるURLをiPhoneのブラウザで開いてください${NC}"
    echo ""

    # トンネル起動（Ctrl+Cで終了）
    trap "kill $STREAMLIT_PID 2>/dev/null; exit" INT TERM
    $CLOUDFLARED tunnel --url http://localhost:$PORT

    kill $STREAMLIT_PID 2>/dev/null
}

start_daemon() {
    echo -e "${CYAN}📅 スケジューラーデーモンを起動中...${NC}"
    $VENV_PYTHON scheduler_daemon.py &
    DAEMON_PID=$!
    echo -e "${GREEN}デーモン起動 (PID: $DAEMON_PID)${NC}"
}

# メイン処理
case "${1:-}" in
    --install)
        install_cloudflared
        ;;
    --tunnel)
        if [ "${2:-}" = "--daemon" ]; then
            start_daemon
        fi
        start_tunnel
        ;;
    --daemon)
        start_daemon
        if [ "${2:-}" = "--tunnel" ]; then
            start_tunnel
        else
            start_local
        fi
        ;;
    --help|-h)
        show_usage
        ;;
    *)
        start_local
        ;;
esac

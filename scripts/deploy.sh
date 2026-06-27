#!/usr/bin/env bash
# 股票分析 Agent — 服务器一键部署脚本
# 用法: bash scripts/deploy.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── 检查 Docker ──
if ! command -v docker &>/dev/null; then
    error "未检测到 Docker，请先安装: https://docs.docker.com/engine/install/"
fi

if docker compose version &>/dev/null; then
    COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE="docker-compose"
else
    error "未检测到 docker compose，请安装 Docker Compose 插件"
fi

info "使用: $COMPOSE"

# ── 检查 .env ──
if [[ ! -f .env ]]; then
    if [[ -f .env.example ]]; then
        warn ".env 不存在，从 .env.example 复制..."
        cp .env.example .env
        error "请编辑 .env 填入 DEEPSEEK_API_KEY 等密钥后重新运行: nano .env"
    else
        error ".env 和 .env.example 均不存在"
    fi
fi

if grep -q "sk-your-deepseek-api-key" .env 2>/dev/null; then
    error ".env 中 DEEPSEEK_API_KEY 仍是占位符，请先填入真实密钥"
fi

# ── 创建持久化目录 ──
mkdir -p logs data_cache .data

# ── 构建并启动 ──
info "构建并启动容器..."
$COMPOSE down --remove-orphans 2>/dev/null || true
$COMPOSE up -d --build

# ── 等待健康检查 ──
info "等待服务就绪..."
PORT="${API__PORT:-8000}"
for i in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
        info "服务已启动 ✓"
        echo ""
        echo "  健康检查:  http://127.0.0.1:${PORT}/health"
        echo "  API 文档:  http://127.0.0.1:${PORT}/api/docs"
        echo "  Web 演示:  http://127.0.0.1:${PORT}/demo"
        echo ""
        echo "  查看日志:  $COMPOSE logs -f"
        echo "  停止服务:  $COMPOSE down"
        exit 0
    fi
    sleep 2
done

error "服务启动超时，请查看日志: $COMPOSE logs"

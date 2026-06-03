#!/usr/bin/env bash
set -euo pipefail

# ────────────────────────────────────────────
# Kubernetes AIOps Agent — Linux 启动脚本
# ────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${GREEN}====================================${NC}"
echo -e "${GREEN}  Kubernetes AIOps Agent 启动脚本${NC}"
echo -e "${GREEN}====================================${NC}"
echo ""

# ── 1. 检查 Python ──
echo -e "${YELLOW}[1/5] 检查 Python 环境...${NC}"
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo -e "${RED}[错误] 未找到 Python，请安装 Python 3.11+${NC}"
    exit 1
fi

PYTHON_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "${GREEN}[成功] Python ${PYTHON_VER}${NC}"
echo ""

# ── 2. 虚拟环境 ──
echo -e "${YELLOW}[2/5] 配置虚拟环境...${NC}"
if [ ! -f .venv/bin/python ]; then
    echo -e "${YELLOW}[信息] 创建虚拟环境...${NC}"
    "$PYTHON" -m venv .venv
fi

if command -v uv &>/dev/null; then
    echo -e "${CYAN}[信息] 使用 uv 同步依赖...${NC}"
    uv sync 2>/dev/null || .venv/bin/pip install -e . -q
else
    .venv/bin/pip install -e . -q
fi
echo -e "${GREEN}[成功] 虚拟环境就绪${NC}"
echo ""

# ── 3. 创建运行时目录 ──
echo -e "${YELLOW}[3/5] 创建运行时目录...${NC}"
mkdir -p logs uploads data/chroma
echo -e "${GREEN}[成功] 目录就绪${NC}"
echo ""

# ── 4. 启动 Kubernetes MCP Server ──
echo -e "${YELLOW}[4/5] 启动 Kubernetes MCP Server...${NC}"
MCP_PID_FILE="mcp_kubernetes.pid"
if [ -f "$MCP_PID_FILE" ] && kill -0 "$(cat "$MCP_PID_FILE")" 2>/dev/null; then
    echo -e "${GREEN}[信息] Kubernetes MCP Server 已在运行中${NC}"
else
    nohup .venv/bin/python mcp_servers/kubernetes_server.py \
        > mcp_kubernetes.log 2>&1 &
    echo $! > "$MCP_PID_FILE"
    sleep 2
    if kill -0 "$(cat "$MCP_PID_FILE")" 2>/dev/null; then
        echo -e "${GREEN}[成功] Kubernetes MCP Server 已启动 (PID: $(cat "$MCP_PID_FILE"))${NC}"
    else
        echo -e "${RED}[错误] Kubernetes MCP Server 启动失败，请查看 mcp_kubernetes.log${NC}"
    fi
fi
echo ""

# ── 5. 启动 FastAPI ──
echo -e "${YELLOW}[5/5] 启动 FastAPI 服务...${NC}"
API_PID_FILE="server.pid"
if [ -f "$API_PID_FILE" ] && kill -0 "$(cat "$API_PID_FILE")" 2>/dev/null; then
    echo -e "${GREEN}[信息] FastAPI 已在运行中${NC}"
else
    nohup .venv/bin/python -m uvicorn app.main:app \
        --host 0.0.0.0 --port 9900 \
        > server.log 2>&1 &
    echo $! > "$API_PID_FILE"
    sleep 3
    if kill -0 "$(cat "$API_PID_FILE")" 2>/dev/null; then
        echo -e "${GREEN}[成功] FastAPI 已启动 (PID: $(cat "$API_PID_FILE"))${NC}"
    else
        echo -e "${RED}[错误] FastAPI 启动失败，请查看 server.log${NC}"
    fi
fi
echo ""

# ── 完成 ──
echo -e "${GREEN}====================================${NC}"
echo -e "${GREEN}  启动完成！${NC}"
echo -e "${GREEN}====================================${NC}"
echo -e "  Web 界面:  ${CYAN}http://localhost:9900${NC}"
echo -e "  API 文档:  ${CYAN}http://localhost:9900/docs${NC}"
echo -e "  MCP Server: ${CYAN}http://localhost:8010/mcp${NC}"
echo -e ""
echo -e "  查看日志:  ${YELLOW}tail -f server.log${NC}"
echo -e "  停止服务:  ${YELLOW}bash stop-linux.sh${NC}"
echo -e "${GREEN}====================================${NC}"

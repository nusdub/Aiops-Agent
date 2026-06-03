#!/usr/bin/env bash
set -euo pipefail

# ────────────────────────────────────────────
# Kubernetes AIOps Agent — Linux 停止脚本
# ────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}====================================${NC}"
echo -e "${GREEN}  停止 Kubernetes AIOps Agent${NC}"
echo -e "${GREEN}====================================${NC}"
echo ""

stop_by_pid_file() {
    local pid_file="$1"
    local name="$2"
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            sleep 1
            # 如果还未退出，强制终止
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null || true
            fi
            echo -e "${GREEN}[成功] ${name} 已停止 (PID: $pid)${NC}"
        else
            echo -e "${YELLOW}[信息] ${name} 进程已不存在 (PID: $pid)${NC}"
        fi
        rm -f "$pid_file"
    else
        echo -e "${YELLOW}[信息] 未找到 ${name} PID 文件${NC}"
    fi
}

# 1. 停止 FastAPI
echo -e "${YELLOW}[1/2] 停止 FastAPI 服务...${NC}"
stop_by_pid_file "server.pid" "FastAPI"
# 兜底：按进程名杀
pkill -f "uvicorn app.main:app" 2>/dev/null && echo -e "${GREEN}[成功] 已停止残留 uvicorn 进程${NC}" || true
echo ""

# 2. 停止 Kubernetes MCP Server
echo -e "${YELLOW}[2/2] 停止 Kubernetes MCP Server...${NC}"
stop_by_pid_file "mcp_kubernetes.pid" "Kubernetes MCP Server"
# 兜底：按进程名杀
pkill -f "mcp_servers/kubernetes_server.py" 2>/dev/null && echo -e "${GREEN}[成功] 已停止残留 MCP 进程${NC}" || true
echo ""

echo -e "${GREEN}====================================${NC}"
echo -e "${GREEN}  所有服务已停止${NC}"
echo -e "${GREEN}====================================${NC}"

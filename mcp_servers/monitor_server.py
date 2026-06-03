"""Monitor MCP Server — 占位实现

TODO: 接入 Prometheus / Grafana / Zabbix 等监控系统。
当前为占位实现，启动后返回健康状态但无实际工具。
"""

from __future__ import annotations

import logging
import os

from fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Monitor_MCP_Server")

mcp = FastMCP("MonitorService")


@mcp.tool()
def health_check() -> dict[str, str]:
    """Monitor MCP Server 健康检查"""
    return {"status": "ok", "message": "Monitor MCP Server 占位运行中，尚未接入监控系统"}


if __name__ == "__main__":
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_MONITOR_PORT", "8004"))
    path = os.getenv("MCP_PATH", "/mcp")
    logger.info("Monitor MCP Server 占位启动，尚未接入真实监控系统")
    mcp.run(transport="streamable-http", host=host, port=port, path=path)

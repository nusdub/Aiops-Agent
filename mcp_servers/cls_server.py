"""CLS (Cloud Log Service) MCP Server — 占位实现

TODO: 接入腾讯云 CLS 日志服务或你使用的日志平台。
当前为占位实现，启动后返回健康状态但无实际工具。
"""

from __future__ import annotations

import logging
import os

from fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("CLS_MCP_Server")

mcp = FastMCP("CLSLogService")


@mcp.tool()
def health_check() -> dict[str, str]:
    """CLS MCP Server 健康检查"""
    return {"status": "ok", "message": "CLS MCP Server 占位运行中，尚未接入日志服务"}


if __name__ == "__main__":
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_CLS_PORT", "8003"))
    path = os.getenv("MCP_PATH", "/mcp")
    logger.info("CLS MCP Server 占位启动，尚未接入真实日志服务")
    mcp.run(transport="streamable-http", host=host, port=port, path=path)

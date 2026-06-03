"""MCP 客户端管理。"""

import asyncio
from typing import Any, cast

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from loguru import logger
from mcp.types import CallToolResult, TextContent

from app.config import config

DEFAULT_MCP_SERVERS = config.mcp_servers
_mcp_client: MultiServerMCPClient | None = None


async def retry_interceptor(
    request: MCPToolCallRequest,
    handler,
    max_retries: int = 3,
    delay: float = 1.0,
) -> CallToolResult:
    """使用指数退避重试 MCP 工具调用。"""
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            logger.info(
                f"调用 MCP 工具: {request.name} "
                f"(服务器: {request.server_name}, 第 {attempt + 1}/{max_retries} 次尝试)"
            )
            result = await handler(request)
            logger.info(f"MCP 工具 {request.name} 调用成功")
            return cast(CallToolResult, result)
        except Exception as exc:
            last_error = exc
            logger.warning(f"MCP 工具 {request.name} 调用失败: {exc}")
            if attempt < max_retries - 1:
                await asyncio.sleep(delay * (2**attempt))

    error_msg = f"工具 {request.name} 在 {max_retries} 次重试后仍然失败: {last_error}"
    logger.error(error_msg)
    return CallToolResult(content=[TextContent(type="text", text=error_msg)], isError=True)


async def get_mcp_client(
    servers: dict[str, dict[str, str]] | None = None,
    tool_interceptors: list | None = None,
    force_new: bool = False,
) -> MultiServerMCPClient:
    """获取 MCP 客户端单例。"""
    global _mcp_client
    if force_new:
        return _create_mcp_client(servers or DEFAULT_MCP_SERVERS, tool_interceptors)
    if _mcp_client is None:
        _mcp_client = _create_mcp_client(servers or DEFAULT_MCP_SERVERS, tool_interceptors)
    return _mcp_client


async def get_mcp_client_with_retry(
    servers: dict[str, dict[str, str]] | None = None,
    tool_interceptors: list | None = None,
    force_new: bool = False,
) -> MultiServerMCPClient:
    """获取带重试拦截器的 MCP 客户端。"""
    interceptors = [retry_interceptor]
    if tool_interceptors:
        interceptors.extend(tool_interceptors)
    return await get_mcp_client(
        servers=servers, tool_interceptors=interceptors, force_new=force_new
    )


def _create_mcp_client(
    servers: dict[str, dict[str, str]],
    tool_interceptors: list | None = None,
) -> MultiServerMCPClient:
    """创建 MCP 客户端实例。"""
    kwargs: dict[str, Any] = {}
    if tool_interceptors:
        kwargs["tool_interceptors"] = tool_interceptors
    return MultiServerMCPClient(servers, **kwargs)  # type: ignore[arg-type]

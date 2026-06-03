"""Kubernetes AIOps MCP Server。

只暴露 Kubernetes 只读工具，写操作统一由 Agent 生成待审批动作，不在 MCP 中执行。
"""

from __future__ import annotations

import functools
import json
import logging
import os
import sys
from typing import Any

from fastmcp import FastMCP

# 确保项目根目录在 sys.path 上，支持独立运行（python mcp_servers/kubernetes_server.py）
# 以及在 Linux 容器中从任意工作目录启动。
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.services.kubernetes_provider import get_kubernetes_provider  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Kubernetes_MCP_Server")

mcp = FastMCP("KubernetesAIOps")


def log_tool_call(func):
    """记录 MCP 工具调用，便于 SRE 排障和审计。"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        method_name = func.__name__
        try:
            logger.info(
                "调用 Kubernetes MCP 工具: %s, 参数: %s",
                method_name,
                json.dumps(kwargs, ensure_ascii=False),
            )
            result = func(*args, **kwargs)
            logger.info("Kubernetes MCP 工具调用成功: %s", method_name)
            return result
        except Exception as exc:
            logger.exception("Kubernetes MCP 工具调用失败: %s", method_name)
            return {"error": str(exc), "tool": method_name}

    return wrapper


def _provider(mode: str = "auto"):
    """获取 Kubernetes Provider"""
    return get_kubernetes_provider(mode)


def _dump(items: list[Any]) -> list[dict[str, Any]]:
    """将 Pydantic 模型列表转成可序列化字典"""
    return [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in items]


@mcp.tool()
@log_tool_call
def get_cluster_overview(mode: str = "auto") -> dict[str, Any]:
    """获取 Kubernetes 集群概览。

    Args:
        mode: 数据源模式，auto/real/demo。auto 优先真实集群，不可用时降级 demo。
    """
    provider = _provider(mode)
    return {"provider_status": provider.status().__dict__, "overview": provider.cluster_overview()}


@mcp.tool()
@log_tool_call
def list_node_health(mode: str = "auto") -> dict[str, Any]:
    """查询 Kubernetes 节点健康状态。"""
    provider = _provider(mode)
    nodes = provider.list_nodes()
    unhealthy = [
        node.name
        for node in nodes
        if not node.ready
        or any(
            condition.status == "True" and condition.type != "Ready"
            for condition in node.conditions
        )
    ]
    return {
        "provider_status": provider.status().__dict__,
        "total": len(nodes),
        "unhealthy_nodes": unhealthy,
        "nodes": _dump(nodes),
    }


@mcp.tool()
@log_tool_call
def list_unhealthy_pods(
    namespace: str = "default", workload: str = "", mode: str = "auto"
) -> dict[str, Any]:
    """查询异常 Pod。

    Args:
        namespace: Kubernetes namespace。
        workload: 可选 workload 名称，用于过滤 Deployment/ReplicaSet/Pod。
        mode: 数据源模式，auto/real/demo。
    """
    provider = _provider(mode)
    pods = provider.list_pods(namespace=namespace, workload=workload)
    unhealthy = [
        pod
        for pod in pods
        if not pod.ready or pod.restart_count > 0 or pod.phase not in {"Running", "Succeeded"}
    ]
    return {
        "provider_status": provider.status().__dict__,
        "namespace": namespace,
        "workload": workload,
        "total": len(unhealthy),
        "pods": _dump(unhealthy),
    }


@mcp.tool()
@log_tool_call
def list_kubernetes_events(
    namespace: str = "default", workload: str = "", mode: str = "auto"
) -> dict[str, Any]:
    """查询 Kubernetes 事件。"""
    provider = _provider(mode)
    events = provider.list_events(namespace=namespace, workload=workload)
    warnings = [event for event in events if event.type.lower() == "warning"]
    return {
        "provider_status": provider.status().__dict__,
        "namespace": namespace,
        "workload": workload,
        "warning_count": len(warnings),
        "events": _dump(events),
    }


@mcp.tool()
@log_tool_call
def get_resource_usage(
    namespace: str = "default", workload: str = "", mode: str = "auto"
) -> dict[str, Any]:
    """查询节点和工作负载资源使用情况。"""
    provider = _provider(mode)
    usage = provider.resource_usage(namespace=namespace, workload=workload)
    return {
        "provider_status": provider.status().__dict__,
        "namespace": namespace,
        "workload": workload,
        "usage": _dump(usage),
    }


@mcp.tool()
@log_tool_call
def check_service_endpoints(
    namespace: str = "default", service_name: str = "", mode: str = "auto"
) -> dict[str, Any]:
    """检查 Service 是否存在 Ready Endpoint。"""
    provider = _provider(mode)
    return {
        "provider_status": provider.status().__dict__,
        "result": provider.service_endpoints(namespace=namespace, service_name=service_name),
    }


if __name__ == "__main__":
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_KUBERNETES_PORT", "8010"))
    path = os.getenv("MCP_PATH", "/mcp")
    mcp.run(transport="streamable-http", host=host, port=port, path=path)

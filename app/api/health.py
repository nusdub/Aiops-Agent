"""健康检查接口"""

from typing import Any

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from loguru import logger

from app.config import config
from app.services.kubernetes_provider import get_kubernetes_provider
from app.services.vector_store_manager import vector_store_manager

router = APIRouter()


def _check_status(status: str, message: str = "", **extra: Any) -> dict[str, Any]:
    """统一 ready 子检查结构，方便部署脚本和面试演示解析。"""
    result: dict[str, Any] = {"status": status}
    if message:
        result["message"] = message
    result.update(extra)
    return result


@router.get("/health")
async def health_check():
    """存活检查：只确认应用进程可响应"""
    health_data: dict[str, Any] = {  # pyright: ignore[reportExplicitAny]
        "service": config.app_name,
        "version": config.app_version,
        "status": "healthy",
    }
    return JSONResponse(
        status_code=200, content={"code": 200, "message": "服务存活", "data": health_data}
    )


@router.get("/ready")
async def readiness_check():
    """就绪检查：确认 Chroma、Kubernetes Provider、MCP 和 LLM 配置状态"""
    checks: dict[str, Any] = {}

    try:
        vector_store_manager.get_vector_store()
        checks["chroma"] = _check_status(
            "ready", "Chroma 向量库可初始化", path=str(config.chroma_path)
        )
    except Exception as e:
        logger.warning(f"Chroma 就绪检查失败: {e}")
        checks["chroma"] = _check_status("error", str(e))

    provider = get_kubernetes_provider(config.k8s_provider_mode)
    provider_status = provider.status()
    checks["kubernetes_provider"] = _check_status(
        "ready" if provider_status.ready else "error",
        provider_status.message,
        name=provider_status.name,
        mode=provider_status.mode,
        ready=provider_status.ready,
    )

    checks["llm"] = {
        "status": "configured"
        if config.dashscope_api_key
        and config.dashscope_api_key.lower() not in {"your-api-key-here", "fake", "test"}
        else "degraded",
        "message": "DashScope Key 已配置"
        if config.dashscope_api_key
        else "未配置 DashScope Key，将只能使用确定性测试 Embedding",
    }

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(config.mcp_kubernetes_url.replace("/mcp", ""))
        checks["mcp_kubernetes"] = _check_status(
            "ready" if response.status_code < 500 else "degraded",
            "Kubernetes MCP HTTP 服务可达",
            http_status=response.status_code,
            url=config.mcp_kubernetes_url,
        )
    except Exception as e:
        checks["mcp_kubernetes"] = _check_status(
            "degraded", f"Kubernetes MCP 暂不可达: {e}", url=config.mcp_kubernetes_url
        )

    hard_fail = (
        checks["chroma"]["status"] == "error"
        or checks["kubernetes_provider"]["status"] == "error"
    )
    degraded = [
        name
        for name, result in checks.items()
        if result["status"] in {"degraded", "error"} and name not in {"chroma", "kubernetes_provider"}
    ]
    status_code = 503 if hard_fail else 200
    overall_status = "ready" if status_code == 200 else "not_ready"
    return JSONResponse(
        status_code=status_code,
        content={
            "code": status_code,
            "message": "服务已就绪" if overall_status == "ready" else "服务未就绪",
            "data": {
                "service": config.app_name,
                "version": config.app_version,
                "status": overall_status,
                "degraded_checks": degraded,
                "checks": checks,
            },
        },
    )

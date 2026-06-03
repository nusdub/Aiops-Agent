"""AIOps 智能运维接口"""

import json

from fastapi import APIRouter
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.models.aiops import AIOpsRequest
from app.services.aiops_service import aiops_service

router = APIRouter()


@router.post("/aiops/diagnose")
async def diagnose_stream(request: AIOpsRequest):
    """Kubernetes AIOps 诊断接口（流式 SSE）"""
    session_id = request.session_id or "default"
    logger.info(f"[会话 {session_id}] 收到 Kubernetes AIOps 诊断请求")

    async def event_generator():
        try:
            async for event in aiops_service.diagnose_request(request):
                yield {"event": "message", "data": json.dumps(event, ensure_ascii=False)}

                if event.get("type") in ["complete", "error"]:
                    break

            logger.info(f"[会话 {session_id}] Kubernetes AIOps 诊断流式响应完成")

        except Exception as e:
            logger.error(f"[会话 {session_id}] AIOps 诊断流式响应异常: {e}", exc_info=True)
            yield {
                "event": "message",
                "data": json.dumps(
                    {"type": "error", "stage": "exception", "message": f"诊断异常: {str(e)}"},
                    ensure_ascii=False,
                ),
            }

    return EventSourceResponse(event_generator())


@router.post("/aiops")
async def legacy_diagnose_stream(request: AIOpsRequest):
    """旧接口兼容：转发到 /api/aiops/diagnose。"""
    return await diagnose_stream(request)

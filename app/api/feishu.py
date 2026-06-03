"""飞书机器人回调接口"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from loguru import logger

from app.models.aiops import AIOpsRequest, AlertPayload
from app.services.aiops_service import aiops_service
from app.services.feishu_service import feishu_service

router = APIRouter()


@router.post("/feishu/events")
async def feishu_events(request: Request, background_tasks: BackgroundTasks):
    """处理飞书事件回调。

    支持 URL verification 和普通文本消息触发 Kubernetes AIOps 诊断。
    """
    payload = await request.json()
    if payload.get("type") == "url_verification":
        if not feishu_service.verify_event_token(payload):
            raise HTTPException(status_code=401, detail="飞书 token 校验失败")
        return {"challenge": payload.get("challenge", "")}

    if not feishu_service.verify_event_token(payload):
        raise HTTPException(status_code=401, detail="飞书 token 校验失败")

    header = payload.get("header", {})
    event_type = header.get("event_type") or payload.get("type")
    if event_type != "im.message.receive_v1":
        logger.info(f"忽略飞书事件: {event_type}")
        return {"ok": True}

    message = feishu_service.extract_message(payload)
    if not message["text"]:
        return {"ok": True, "message": "空消息已忽略"}

    background_tasks.add_task(_diagnose_and_reply, message["message_id"], message["text"])
    return {"ok": True}


async def _diagnose_and_reply(message_id: str, text: str) -> None:
    """后台执行诊断并回复飞书"""
    request = AIOpsRequest(
        session_id=message_id or "feishu",
        mode="auto",
        namespace="default",
        question=text,
        alert=AlertPayload(name="FeishuUserQuestion", severity="warning", summary=text),
    )
    report = ""
    async for event in aiops_service.diagnose_request(request):
        if event.get("type") == "report":
            report = event.get("report", "")
    if not report:
        report = "诊断未生成报告，请检查服务日志。"
    # 飞书文本消息有长度限制（约 3500 字符），超长时截断并记录
    if len(report) > 3500:
        logger.warning(f"诊断报告超长({len(report)}字符)，将截断至 3500 字符")
        report = report[:3500]
    try:
        await feishu_service.reply_text(message_id, report)
    except Exception as exc:
        logger.warning(f"飞书消息回复失败，尝试 webhook 推送: {exc}")
        await feishu_service.send_webhook_text(report)

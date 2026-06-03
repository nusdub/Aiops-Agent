"""飞书机器人集成服务。

支持事件回调校验、消息解析、tenant token 获取和文本回复。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, cast

import httpx
from loguru import logger

from app.config import config


class FeishuService:
    """飞书通知与回调处理"""

    def verify_event_token(self, payload: dict[str, Any]) -> bool:
        """校验飞书事件 verification token"""
        expected = config.feishu_verification_token
        if not expected:
            return True
        token = payload.get("token") or payload.get("header", {}).get("token")
        return bool(token == expected)

    def build_custom_bot_sign(self, timestamp: int | None = None) -> tuple[str, str]:
        """生成飞书自定义机器人签名"""
        ts = str(timestamp or int(time.time()))
        string_to_sign = f"{ts}\n{config.feishu_webhook_secret}"
        digest = hmac.new(string_to_sign.encode("utf-8"), b"", digestmod=hashlib.sha256).digest()
        return ts, base64.b64encode(digest).decode("utf-8")

    async def send_webhook_text(self, text: str) -> bool:
        """通过自定义机器人 webhook 推送文本"""
        if not config.feishu_webhook_url:
            logger.info("未配置飞书 webhook，跳过推送")
            return False
        payload: dict[str, Any] = {"msg_type": "text", "content": {"text": text}}
        if config.feishu_webhook_secret:
            timestamp, sign = self.build_custom_bot_sign()
            payload["timestamp"] = timestamp
            payload["sign"] = sign
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(config.feishu_webhook_url, json=payload)
        ok = response.status_code < 300
        if not ok:
            logger.warning(f"飞书 webhook 推送失败: {response.status_code} {response.text}")
        return ok

    async def get_tenant_access_token(self) -> str:
        """获取 tenant access token"""
        if not config.feishu_app_id or not config.feishu_app_secret:
            raise RuntimeError("未配置 FEISHU_APP_ID 或 FEISHU_APP_SECRET")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": config.feishu_app_id, "app_secret": config.feishu_app_secret},
            )
        response.raise_for_status()
        data = response.json()
        token = data.get("tenant_access_token")
        if not token:
            raise RuntimeError(f"获取 tenant_access_token 失败: {data}")
        return cast(str, token)

    async def reply_text(self, message_id: str, text: str) -> bool:
        """回复飞书消息"""
        if not message_id:
            return False
        token = await self.get_tenant_access_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "msg_type": "text",
                    "content": json.dumps({"text": text}, ensure_ascii=False),
                },
            )
        ok = response.status_code < 300
        if not ok:
            logger.warning(f"飞书消息回复失败: {response.status_code} {response.text}")
        return ok

    def extract_message(self, payload: dict[str, Any]) -> dict[str, str]:
        """从飞书事件中解析文本消息"""
        event = payload.get("event", {})
        message = event.get("message", {})
        content = message.get("content", "{}")
        try:
            content_data = json.loads(content)
        except json.JSONDecodeError:
            content_data = {"text": content}
        return {
            "message_id": message.get("message_id", ""),
            "chat_id": message.get("chat_id", ""),
            "text": content_data.get("text", "").strip(),
        }


feishu_service = FeishuService()

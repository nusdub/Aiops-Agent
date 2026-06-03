from app.services.feishu_service import FeishuService


def test_extract_feishu_text_message():
    service = FeishuService()
    payload = {
        "event": {
            "message": {
                "message_id": "om_123",
                "chat_id": "oc_123",
                "content": '{"text":"诊断 checkout-api"}',
            }
        }
    }

    message = service.extract_message(payload)

    assert message["message_id"] == "om_123"
    assert message["text"] == "诊断 checkout-api"


def test_custom_bot_sign_shape(monkeypatch):
    service = FeishuService()
    monkeypatch.setattr("app.config.config.feishu_webhook_secret", "secret")

    timestamp, sign = service.build_custom_bot_sign(timestamp=1700000000)

    assert timestamp == "1700000000"
    assert sign

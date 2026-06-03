import pytest

from app.models.aiops import AIOpsRequest, AlertPayload
from app.services.aiops_service import aiops_service


@pytest.mark.asyncio
async def test_aiops_diagnose_demo_event_contract():
    request = AIOpsRequest(
        session_id="test",
        mode="demo",
        namespace="prod",
        workload="checkout-api",
        question="checkout-api 持续重启",
        alert=AlertPayload(name="KubePodCrashLooping", severity="critical", summary="Pod 重启"),
    )

    events = [event async for event in aiops_service.diagnose_request(request)]
    event_types = [event["type"] for event in events]

    assert "incident" in event_types
    assert "evidence" in event_types
    assert "hypothesis" in event_types
    assert "action_plan" in event_types
    assert event_types[-1] == "complete"

    complete = events[-1]
    assert complete["diagnosis"]["evidence_count"] >= 5
    assert complete["diagnosis"]["trace_id"].startswith("diag-")
    assert complete["diagnosis"]["duration_ms"] >= 0
    assert complete["diagnosis"]["risk_summary"]["action_count"] >= 1
    assert complete["diagnosis"]["risk_summary"]["requires_human_approval_count"] >= 1
    assert complete["diagnosis"]["evidence_coverage"]["coverage_ratio"] == 1.0
    assert complete["diagnosis"]["next_steps"]
    assert complete["diagnosis"]["actions"][0]["requires_human_approval"] is True
    assert "## 风险摘要" in complete["diagnosis"]["report"]
    assert "## 下一步" in complete["diagnosis"]["report"]
    assert "ev-pod-health" in complete["diagnosis"]["report"]

"""AIOps 请求和响应模型"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AlertPayload(BaseModel):
    """告警输入载荷"""

    name: str = Field(default="KubernetesHealthCheck", description="告警名称")
    severity: Literal["info", "warning", "critical"] = Field(
        default="warning", description="告警级别"
    )
    summary: str = Field(default="", description="告警摘要")
    labels: dict[str, str] = Field(default_factory=dict, description="告警标签")
    annotations: dict[str, str] = Field(default_factory=dict, description="告警注解")


class AIOpsRequest(BaseModel):
    """AIOps 诊断请求"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "session-123",
                "mode": "auto",
                "cluster": "prod-a",
                "namespace": "prod",
                "workload": "checkout-api",
                "question": "服务 5xx 突增，请诊断根因",
                "alert": {
                    "name": "KubePodCrashLooping",
                    "severity": "critical",
                    "summary": "checkout-api Pod 持续重启",
                    "labels": {"service": "checkout-api"},
                },
            }
        }
    )

    session_id: str | None = Field(default="default", description="会话ID，用于追踪诊断历史")
    mode: Literal["auto", "real", "demo"] = Field(
        default="auto", description="Kubernetes 数据源模式"
    )
    cluster: str = Field(default="default", description="集群名称")
    namespace: str = Field(default="default", description="Kubernetes namespace")
    workload: str = Field(default="", description="Deployment/Pod/Service 等工作负载名称")
    alert: AlertPayload | None = Field(default=None, description="告警输入")
    question: str = Field(default="", description="用户补充问题")
    time_window_minutes: int = Field(default=30, ge=1, le=1440, description="诊断时间窗")
    include_actions: bool = Field(default=True, description="是否输出可审批处置建议")


class AlertInfo(BaseModel):
    """告警信息"""

    alertname: str
    severity: str
    instance: str
    duration: str
    description: str | None = None


class DiagnosisResponse(BaseModel):
    """诊断响应（非流式）"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": 200,
                "message": "success",
                "data": {
                    "status": "completed",
                    "target_alert": {"alertname": "HighCPUUsage", "severity": "critical"},
                    "diagnosis": {
                        "root_cause": "数据库连接池耗尽",
                        "recommendations": ["扩容数据库连接池", "优化SQL查询"],
                    },
                },
            }
        }
    )

    code: int = 200
    message: str = "success"
    data: dict[str, Any]

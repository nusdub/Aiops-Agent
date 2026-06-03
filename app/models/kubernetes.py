"""Kubernetes AIOps 领域模型。

这些模型用于把 Kubernetes API、Demo Provider 和 Agent 推理结果统一成可审计的证据链。
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class K8sCondition(BaseModel):
    """Kubernetes 条件状态"""

    type: str
    status: str
    reason: str = ""
    message: str = ""


class K8sNodeSummary(BaseModel):
    """节点健康摘要"""

    name: str
    ready: bool
    roles: list[str] = Field(default_factory=list)
    cpu_capacity: str = ""
    memory_capacity: str = ""
    cpu_allocatable: str = ""
    memory_allocatable: str = ""
    conditions: list[K8sCondition] = Field(default_factory=list)


class K8sPodSummary(BaseModel):
    """Pod 健康摘要"""

    name: str
    namespace: str
    workload: str = ""
    phase: str
    node_name: str = ""
    restart_count: int = 0
    ready: bool = False
    reason: str = ""
    message: str = ""
    container_images: list[str] = Field(default_factory=list)


class K8sEventSummary(BaseModel):
    """Kubernetes 事件摘要"""

    namespace: str
    involved_object: str
    reason: str
    message: str
    type: str = "Normal"
    count: int = 1
    last_timestamp: str = ""


class K8sMetricPoint(BaseModel):
    """资源指标摘要"""

    namespace: str = ""
    name: str
    kind: Literal["node", "pod", "workload", "cluster"]
    cpu: str = ""
    memory: str = ""
    note: str = ""


class K8sEvidence(BaseModel):
    """Agent 可引用的证据项"""

    evidence_id: str
    source: str
    title: str
    severity: Literal["info", "warning", "critical"] = "info"
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


class K8sActionPlan(BaseModel):
    """只读 Agent 生成的可审批处置建议"""

    action_id: str
    title: str
    risk_level: Literal["low", "medium", "high"]
    command_or_patch: str
    rollback: str
    evidence_ids: list[str] = Field(default_factory=list)
    requires_human_approval: bool = True


class K8sIncident(BaseModel):
    """归一化后的告警/问题输入"""

    session_id: str
    cluster: str = "default"
    namespace: str = "default"
    workload: str = ""
    alert_name: str = "KubernetesHealthCheck"
    severity: Literal["info", "warning", "critical"] = "warning"
    question: str = "请诊断当前 Kubernetes 集群健康状态"
    time_window_minutes: int = 30
    mode: Literal["auto", "real", "demo"] = "auto"

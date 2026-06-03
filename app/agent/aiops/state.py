"""Kubernetes AIOps Agent 状态定义"""

from typing import Any, TypedDict

from app.models.kubernetes import K8sActionPlan, K8sEvidence, K8sIncident


class Hypothesis(TypedDict):
    """根因假设"""

    hypothesis_id: str
    title: str
    confidence: float
    severity: str
    evidence_ids: list[str]
    reasoning: str


class AIOpsState(TypedDict):
    """Kubernetes AIOps 诊断状态"""

    request: dict[str, Any]
    incident: K8sIncident | None
    runbooks: list[dict[str, Any]]
    evidence: list[K8sEvidence]
    hypotheses: list[Hypothesis]
    actions: list[K8sActionPlan]
    report: str
    errors: list[str]

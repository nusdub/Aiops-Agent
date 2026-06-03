"""Kubernetes AIOps Agent 服务。

核心原则：先收集证据，再形成假设，所有结论必须引用 evidence_id。
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from time import perf_counter
from typing import Any, Literal, cast
from uuid import uuid4

from langchain_core.documents import Document
from loguru import logger

from app.agent.aiops.state import Hypothesis
from app.config import config
from app.models.aiops import AIOpsRequest
from app.models.kubernetes import K8sActionPlan, K8sEvidence, K8sIncident
from app.services.kubernetes_provider import get_kubernetes_provider
from app.services.vector_store_manager import vector_store_manager


class AIOpsService:
    """告警驱动 Kubernetes AIOps Agent"""

    def __init__(self) -> None:
        """初始化服务"""
        logger.info("Kubernetes AIOps Agent 初始化完成")

    async def diagnose_request(self, request: AIOpsRequest) -> AsyncGenerator[dict[str, Any], None]:
        """执行结构化 Kubernetes 诊断流程"""
        session_id = request.session_id or "default"
        trace_id = f"diag-{uuid4().hex[:12]}"
        started_at = perf_counter()
        logger.info(f"[会话 {session_id}][追踪 {trace_id}] 开始 Kubernetes AIOps 诊断")

        def event(event_type: str, stage: str, message: str, **payload: Any) -> dict[str, Any]:
            """为本次诊断流统一追加追踪 ID，方便面试演示和线上排障。"""
            return self._event(event_type, stage, message, trace_id=trace_id, **payload)

        try:
            yield event("status", "normalize_incident", "正在归一化告警输入")
            incident = self._normalize_incident(request)
            yield event(
                "incident",
                "incident_normalized",
                "告警输入已归一化",
                incident=incident.model_dump(),
            )

            yield event("status", "retrieve_runbooks", "正在检索 Kubernetes 运维手册")
            runbooks = self._retrieve_runbooks(incident)
            yield event(
                "evidence", "runbooks_retrieved", "Runbook 检索完成", runbooks=runbooks
            )

            yield event(
                "status", "collect_evidence", "正在通过 Kubernetes MCP/Provider 收集证据"
            )
            evidence = self._collect_evidence(incident)
            for item in evidence:
                yield event(
                    "evidence",
                    "evidence_collected",
                    item.title,
                    evidence=item.model_dump(),
                )

            yield event("status", "rank_hypotheses", "正在排序根因假设")
            hypotheses = self._rank_hypotheses(incident, evidence, runbooks)
            yield event(
                "hypothesis", "hypotheses_ranked", "根因假设排序完成", hypotheses=hypotheses
            )

            actions: list[K8sActionPlan] = []
            if request.include_actions:
                yield event("status", "build_actions", "正在生成可审批处置建议")
                actions = self._build_actions(incident, evidence, hypotheses)
                yield event(
                    "action_plan",
                    "actions_created",
                    "处置建议已生成，默认需要人工审批",
                    actions=[action.model_dump() for action in actions],
                )

            risk_summary = self._build_risk_summary(actions)
            evidence_coverage = self._build_evidence_coverage(evidence, hypotheses)
            next_steps = self._build_next_steps(incident, hypotheses, actions)

            yield event("status", "render_report", "正在生成诊断报告")
            report = self._render_report(
                incident,
                runbooks,
                evidence,
                hypotheses,
                actions,
                risk_summary,
                evidence_coverage,
                next_steps,
            )
            yield event("report", "report_created", "诊断报告已生成", report=report)

            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            yield event(
                "complete",
                "diagnosis_complete",
                "诊断流程完成",
                diagnosis={
                    "status": "completed",
                    "trace_id": trace_id,
                    "duration_ms": duration_ms,
                    "incident": incident.model_dump(),
                    "evidence_count": len(evidence),
                    "evidence_coverage": evidence_coverage,
                    "hypotheses": hypotheses,
                    "risk_summary": risk_summary,
                    "next_steps": next_steps,
                    "actions": [action.model_dump() for action in actions],
                    "report": report,
                },
            )
        except Exception as exc:
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            logger.error(
                f"[会话 {session_id}][追踪 {trace_id}] Kubernetes AIOps 诊断失败: {exc}",
                exc_info=True,
            )
            yield event(
                "error",
                "error",
                f"诊断过程发生错误: {exc}",
                duration_ms=duration_ms,
            )

    async def diagnose(self, session_id: str = "default") -> AsyncGenerator[dict[str, Any], None]:
        """兼容旧接口：无输入时执行默认 Kubernetes 健康诊断"""
        request = AIOpsRequest(session_id=session_id, mode="auto", namespace=config.k8s_namespace)
        async for event in self.diagnose_request(request):
            yield event

    def _normalize_incident(self, request: AIOpsRequest) -> K8sIncident:
        """归一化告警/问题输入"""
        alert = request.alert
        alert_name = alert.name if alert else "KubernetesHealthCheck"
        severity = alert.severity if alert else "warning"
        question_parts = []
        if alert and alert.summary:
            question_parts.append(alert.summary)
        if request.question:
            question_parts.append(request.question)
        question = "；".join(question_parts) or "请诊断当前 Kubernetes 集群健康状态"
        workload = request.workload
        if not workload and alert:
            workload = (
                alert.labels.get("workload")
                or alert.labels.get("service")
                or alert.labels.get("app", "")
            )
        return K8sIncident(
            session_id=request.session_id or "default",
            cluster=request.cluster,
            namespace=request.namespace,
            workload=workload,
            alert_name=alert_name,
            severity=severity,
            question=question,
            time_window_minutes=request.time_window_minutes,
            mode=request.mode,
        )

    def _retrieve_runbooks(self, incident: K8sIncident) -> list[dict[str, Any]]:
        """从 Chroma 检索 Kubernetes 运维知识"""
        query = f"{incident.alert_name} {incident.workload} {incident.question} Kubernetes 故障处理"
        try:
            docs: list[Document] = vector_store_manager.similarity_search(query, k=config.rag_top_k)
        except Exception as exc:
            logger.warning(f"Runbook 检索失败: {exc}")
            docs = []
        return [
            {
                "runbook_id": f"runbook-{index}",
                "source": doc.metadata.get("_source")
                or doc.metadata.get("_file_name")
                or "unknown",
                "title": doc.metadata.get("h1") or doc.metadata.get("h2") or "Kubernetes 运维手册",
                "content": doc.page_content[:1200],
            }
            for index, doc in enumerate(docs, 1)
        ]

    def _collect_evidence(self, incident: K8sIncident) -> list[K8sEvidence]:
        """收集 Kubernetes 证据"""
        provider = get_kubernetes_provider(incident.mode)
        evidence: list[K8sEvidence] = []

        overview = provider.cluster_overview()
        evidence.append(
            K8sEvidence(
                evidence_id="ev-cluster-overview",
                source=f"kubernetes:{provider.status().mode}",
                title="集群概览",
                severity="warning" if overview.get("unhealthy_pod_count", 0) else "info",
                summary=f"集群节点数 {overview.get('node_count')}，异常 Pod 数 {overview.get('unhealthy_pod_count', 0)}",
                data=overview,
            )
        )

        nodes = provider.list_nodes()
        unhealthy_nodes = [
            node
            for node in nodes
            if not node.ready
            or any(
                condition.status == "True" and condition.type != "Ready"
                for condition in node.conditions
            )
        ]
        evidence.append(
            K8sEvidence(
                evidence_id="ev-node-health",
                source=f"kubernetes:{provider.status().mode}",
                title="节点健康状态",
                severity="critical" if unhealthy_nodes else "info",
                summary=f"发现 {len(unhealthy_nodes)} 个存在压力或不可用条件的节点",
                data={"nodes": [node.model_dump() for node in nodes]},
            )
        )

        pods = provider.list_pods(namespace=incident.namespace, workload=incident.workload)
        unhealthy_pods = [
            pod
            for pod in pods
            if not pod.ready or pod.restart_count > 0 or pod.phase not in {"Running", "Succeeded"}
        ]
        evidence.append(
            K8sEvidence(
                evidence_id="ev-pod-health",
                source=f"kubernetes:{provider.status().mode}",
                title="Pod 健康状态",
                severity="critical" if unhealthy_pods else "info",
                summary=f"发现 {len(unhealthy_pods)} 个异常 Pod",
                data={"pods": [pod.model_dump() for pod in unhealthy_pods or pods]},
            )
        )

        events = provider.list_events(namespace=incident.namespace, workload=incident.workload)
        warning_events = [event for event in events if event.type.lower() == "warning"]
        evidence.append(
            K8sEvidence(
                evidence_id="ev-events",
                source=f"kubernetes:{provider.status().mode}",
                title="Kubernetes 事件",
                severity="critical" if warning_events else "info",
                summary=f"诊断窗口内发现 {len(warning_events)} 条 Warning 事件",
                data={"events": [event.model_dump() for event in events]},
            )
        )

        usage = provider.resource_usage(namespace=incident.namespace, workload=incident.workload)
        evidence.append(
            K8sEvidence(
                evidence_id="ev-resource-usage",
                source=f"kubernetes:{provider.status().mode}",
                title="资源使用情况",
                severity="warning"
                if any("接近" in point.note or "压力" in point.note for point in usage)
                else "info",
                summary="已采集节点/工作负载资源使用摘要",
                data={"usage": [point.model_dump() for point in usage]},
            )
        )

        service_name = incident.workload
        if service_name:
            endpoint_result = provider.service_endpoints(
                namespace=incident.namespace, service_name=service_name
            )
            severity: Literal["info", "critical"] = (
                "critical"
                if endpoint_result.get("service_exists")
                and endpoint_result.get("endpoint_count", 0) == 0
                else "info"
            )
            evidence.append(
                K8sEvidence(
                    evidence_id="ev-service-endpoints",
                    source=f"kubernetes:{provider.status().mode}",
                    title="Service Endpoint 状态",
                    severity=severity,
                    summary=cast(str, endpoint_result.get("message", "Service Endpoint 检查完成")),
                    data=endpoint_result,
                )
            )

        return evidence

    def _rank_hypotheses(
        self,
        incident: K8sIncident,
        evidence: list[K8sEvidence],
        runbooks: list[dict[str, Any]],
    ) -> list[Hypothesis]:
        """基于证据生成根因假设"""
        hypotheses: list[Hypothesis] = []
        by_id = {item.evidence_id: item for item in evidence}
        pod_data = by_id.get("ev-pod-health")
        event_data = by_id.get("ev-events")
        endpoint_data = by_id.get("ev-service-endpoints")
        node_data = by_id.get("ev-node-health")

        pod_text = json.dumps(pod_data.data if pod_data else {}, ensure_ascii=False)
        event_text = json.dumps(event_data.data if event_data else {}, ensure_ascii=False)
        if "CrashLoopBackOff" in pod_text or "BackOff" in event_text:
            hypotheses.append(
                Hypothesis(
                    hypothesis_id="h-crashloop",
                    title=f"{incident.workload or '目标工作负载'} Pod 持续重启导致服务不可用",
                    confidence=0.9,
                    severity="critical",
                    evidence_ids=["ev-pod-health", "ev-events"],
                    reasoning="Pod 状态和事件中同时出现 CrashLoopBackOff/BackOff，符合启动失败或依赖异常特征。",
                )
            )
        if endpoint_data and endpoint_data.data.get("endpoint_count", 1) == 0:
            hypotheses.append(
                Hypothesis(
                    hypothesis_id="h-no-ready-endpoints",
                    title="Service 没有 Ready Endpoint，流量无法转发到健康 Pod",
                    confidence=0.86,
                    severity="critical",
                    evidence_ids=["ev-service-endpoints", "ev-pod-health"],
                    reasoning="Service 存在但 ready endpoint 为 0，通常由 Pod 未就绪或 selector 不匹配导致。",
                )
            )
        node_text = json.dumps(node_data.data if node_data else {}, ensure_ascii=False)
        if "MemoryPressure" in node_text:
            hypotheses.append(
                Hypothesis(
                    hypothesis_id="h-node-memory-pressure",
                    title="节点 MemoryPressure 可能放大 Pod 不稳定",
                    confidence=0.68,
                    severity="warning",
                    evidence_ids=["ev-node-health", "ev-resource-usage"],
                    reasoning="节点条件中出现 MemoryPressure，需要确认是否存在驱逐、OOM 或资源争抢。",
                )
            )
        if runbooks and hypotheses:
            hypotheses[0]["reasoning"] += " 已检索到相关 Runbook，可按知识库建议执行人工确认。"
        if not hypotheses:
            hypotheses.append(
                Hypothesis(
                    hypothesis_id="h-insufficient-evidence",
                    title="证据不足，暂无法确认单一根因",
                    confidence=0.35,
                    severity=incident.severity,
                    evidence_ids=[item.evidence_id for item in evidence],
                    reasoning="当前证据未呈现明确 CrashLoop、Endpoint、节点压力等强特征，需要人工补充日志或指标。",
                )
            )
        return sorted(hypotheses, key=lambda item: item["confidence"], reverse=True)

    def _build_actions(
        self,
        incident: K8sIncident,
        evidence: list[K8sEvidence],
        hypotheses: list[Hypothesis],
    ) -> list[K8sActionPlan]:
        """生成只读可审批处置建议"""
        actions: list[K8sActionPlan] = []
        top_ids = {hypothesis["hypothesis_id"] for hypothesis in hypotheses[:2]}
        namespace = incident.namespace
        workload = incident.workload or "<workload>"

        if "h-crashloop" in top_ids:
            actions.append(
                K8sActionPlan(
                    action_id="act-inspect-crashloop",
                    title="审批后查看重启 Pod 的日志和上一轮容器日志",
                    risk_level="low",
                    command_or_patch=(
                        f"kubectl -n {namespace} logs deploy/{workload} --all-containers --tail=120\n"
                        f"kubectl -n {namespace} logs deploy/{workload} --all-containers --previous --tail=120"
                    ),
                    rollback="只读命令，无需回滚。",
                    evidence_ids=["ev-pod-health", "ev-events"],
                )
            )
            actions.append(
                K8sActionPlan(
                    action_id="act-rollout-rollback",
                    title="审批后回滚到上一个稳定版本",
                    risk_level="medium",
                    command_or_patch=f"kubectl -n {namespace} rollout undo deployment/{workload}",
                    rollback=f"kubectl -n {namespace} rollout history deployment/{workload} 后选择稳定 revision 重新回滚。",
                    evidence_ids=["ev-pod-health", "ev-events"],
                )
            )
        if "h-no-ready-endpoints" in top_ids:
            actions.append(
                K8sActionPlan(
                    action_id="act-check-service-selector",
                    title="审批后核对 Service selector 与 Pod labels",
                    risk_level="low",
                    command_or_patch=(
                        f"kubectl -n {namespace} get svc {workload} -o yaml\n"
                        f"kubectl -n {namespace} get pods -l app={workload} --show-labels"
                    ),
                    rollback="只读命令，无需回滚。",
                    evidence_ids=["ev-service-endpoints", "ev-pod-health"],
                )
            )
        if "h-node-memory-pressure" in top_ids:
            actions.append(
                K8sActionPlan(
                    action_id="act-drain-pressure-node",
                    title="审批后将压力节点临时隔离并迁移业务",
                    risk_level="high",
                    command_or_patch="kubectl cordon <node>\nkubectl drain <node> --ignore-daemonsets --delete-emptydir-data",
                    rollback="kubectl uncordon <node>",
                    evidence_ids=["ev-node-health", "ev-resource-usage"],
                )
            )
        if not actions:
            actions.append(
                K8sActionPlan(
                    action_id="act-collect-more-evidence",
                    title="补充日志、事件和指标后再执行处置",
                    risk_level="low",
                    command_or_patch=(
                        f"kubectl -n {namespace} describe deploy/{workload}\n"
                        f"kubectl -n {namespace} get events --sort-by=.lastTimestamp | tail -50"
                    ),
                    rollback="只读命令，无需回滚。",
                    evidence_ids=[item.evidence_id for item in evidence],
                )
            )
        return actions

    def _build_risk_summary(self, actions: list[K8sActionPlan]) -> dict[str, Any]:
        """汇总处置建议风险，突出 Agent 只读和人工审批边界。"""
        risk_order = {"low": 1, "medium": 2, "high": 3}
        counts = {"low": 0, "medium": 0, "high": 0}
        for action in actions:
            counts[action.risk_level] += 1
        highest_risk = max(
            (action.risk_level for action in actions),
            key=lambda level: risk_order[level],
            default="low",
        )
        approval_count = sum(1 for action in actions if action.requires_human_approval)
        return {
            "highest_risk": highest_risk,
            "risk_counts": counts,
            "action_count": len(actions),
            "requires_human_approval_count": approval_count,
            "safety_boundary": "Agent 只做诊断和建议，不直接执行 Kubernetes 写操作。",
        }

    def _build_evidence_coverage(
        self,
        evidence: list[K8sEvidence],
        hypotheses: list[Hypothesis],
    ) -> dict[str, Any]:
        """统计证据覆盖情况，便于 SRE 面试说明诊断可信度。"""
        collected_ids = {item.evidence_id for item in evidence}
        referenced_ids = {
            evidence_id
            for hypothesis in hypotheses
            for evidence_id in hypothesis.get("evidence_ids", [])
        }
        return {
            "collected_evidence_ids": sorted(collected_ids),
            "referenced_evidence_ids": sorted(referenced_ids),
            "missing_referenced_evidence_ids": sorted(referenced_ids - collected_ids),
            "critical_count": sum(1 for item in evidence if item.severity == "critical"),
            "warning_count": sum(1 for item in evidence if item.severity == "warning"),
            "coverage_ratio": 1.0 if not referenced_ids else round(
                len(referenced_ids & collected_ids) / len(referenced_ids), 2
            ),
        }

    def _build_next_steps(
        self,
        incident: K8sIncident,
        hypotheses: list[Hypothesis],
        actions: list[K8sActionPlan],
    ) -> list[str]:
        """生成面向值班 SRE 的下一步动作，保持简洁可执行。"""
        top = hypotheses[0] if hypotheses else None
        steps = [
            f"用 trace_id 关联本次诊断日志，并复核 namespace={incident.namespace}、workload={incident.workload or '未指定'} 是否准确。",
        ]
        if top:
            steps.append(
                f"优先验证最高置信假设 {top['hypothesis_id']}：{top['title']}。"
            )
        if actions:
            first_action = actions[0]
            steps.append(
                f"先执行低风险只读检查 {first_action.action_id}，确认后再评估中高风险变更。"
            )
        steps.append("任何写操作必须人工审批，并在执行前确认影响面、回滚命令和维护窗口。")
        return steps

    def _render_report(
        self,
        incident: K8sIncident,
        runbooks: list[dict[str, Any]],
        evidence: list[K8sEvidence],
        hypotheses: list[Hypothesis],
        actions: list[K8sActionPlan],
        risk_summary: dict[str, Any],
        evidence_coverage: dict[str, Any],
        next_steps: list[str],
    ) -> str:
        """生成 Markdown 诊断报告"""
        top = hypotheses[0]
        lines = [
            "# Kubernetes AIOps 诊断报告",
            "",
            "## 告警概览",
            f"- 集群: {incident.cluster}",
            f"- Namespace: {incident.namespace}",
            f"- Workload: {incident.workload or '未指定'}",
            f"- 告警: {incident.alert_name} / {incident.severity}",
            f"- 问题: {incident.question}",
            "",
            "## 根因判断",
            f"- 最可能根因: {top['title']}",
            f"- 置信度: {top['confidence']:.2f}",
            f"- 依据: {', '.join(top['evidence_ids'])}",
            f"- 推理: {top['reasoning']}",
            f"- 证据覆盖率: {evidence_coverage['coverage_ratio']:.2f}",
            "",
            "## 证据链",
        ]
        for item in evidence:
            lines.append(f"- [{item.evidence_id}] {item.title}: {item.summary}")
        lines.extend(
            [
                "",
                "## 风险摘要",
                f"- 最高风险等级: {risk_summary['highest_risk']}",
                f"- 建议数量: {risk_summary['action_count']}，需人工审批: {risk_summary['requires_human_approval_count']}",
                f"- 安全边界: {risk_summary['safety_boundary']}",
            ]
        )
        lines.extend(["", "## 处置建议"])
        for action in actions:
            lines.append(
                f"- [{action.action_id}] {action.title}，风险: {action.risk_level}，需要人工审批: {action.requires_human_approval}，依据: {', '.join(action.evidence_ids)}"
            )
            lines.append(f"  - 命令/补丁: {action.command_or_patch}")
            lines.append(f"  - 回滚: {action.rollback}")
        lines.extend(["", "## 下一步"])
        for step in next_steps:
            lines.append(f"- {step}")
        lines.extend(["", "## Runbook 命中"])
        if runbooks:
            for runbook in runbooks:
                lines.append(f"- {runbook['runbook_id']}: {runbook['title']} ({runbook['source']})")
        else:
            lines.append("- 未命中相关 Runbook，建议补充 Kubernetes 故障案例库。")
        lines.extend(
            [
                "",
                "## 安全边界",
                "- 当前 Agent 默认只读诊断，不直接修改集群。",
                "- 所有写操作仅作为审批建议输出，执行前需人工确认影响面和回滚方案。",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _event(event_type: str, stage: str, message: str, **payload: Any) -> dict[str, Any]:
        """构造 SSE 事件"""
        return {"type": event_type, "stage": stage, "message": message, **payload}


aiops_service = AIOpsService()

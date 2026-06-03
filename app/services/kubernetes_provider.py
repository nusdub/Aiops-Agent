"""Kubernetes 数据 Provider。

Real Provider 只读访问 Kubernetes API；Demo Provider 生成稳定样例，保证没有真实集群时也能演示。
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.config import config
from app.models.kubernetes import (
    K8sCondition,
    K8sEventSummary,
    K8sMetricPoint,
    K8sNodeSummary,
    K8sPodSummary,
)


@dataclass(frozen=True)
class ProviderStatus:
    """Provider 就绪状态"""

    name: str
    mode: str
    ready: bool
    message: str


class KubernetesProvider(ABC):
    """Kubernetes 只读数据源接口"""

    mode: str

    @abstractmethod
    def status(self) -> ProviderStatus:
        """返回 Provider 状态"""

    @abstractmethod
    def cluster_overview(self) -> dict[str, Any]:
        """获取集群概览"""

    @abstractmethod
    def list_nodes(self) -> list[K8sNodeSummary]:
        """获取节点列表"""

    @abstractmethod
    def list_pods(self, namespace: str = "default", workload: str = "") -> list[K8sPodSummary]:
        """获取 Pod 列表"""

    @abstractmethod
    def list_events(self, namespace: str = "default", workload: str = "") -> list[K8sEventSummary]:
        """获取事件列表"""

    @abstractmethod
    def resource_usage(
        self, namespace: str = "default", workload: str = ""
    ) -> list[K8sMetricPoint]:
        """获取资源使用情况"""

    @abstractmethod
    def service_endpoints(
        self, namespace: str = "default", service_name: str = ""
    ) -> dict[str, Any]:
        """获取 Service/Endpoint 检查结果"""


class DemoKubernetesProvider(KubernetesProvider):
    """稳定可复现的 Kubernetes Demo 数据源"""

    mode = "demo"

    def status(self) -> ProviderStatus:
        """返回 Demo Provider 状态"""
        return ProviderStatus(
            name="demo-kubernetes-provider",
            mode=self.mode,
            ready=True,
            message="Demo Kubernetes Provider 已就绪",
        )

    def cluster_overview(self) -> dict[str, Any]:
        """返回一个包含典型故障的 Demo 集群概览"""
        return {
            "cluster": "demo-kind",
            "provider": self.mode,
            "node_count": 3,
            "namespace_count": 5,
            "unhealthy_pod_count": 2,
            "critical_findings": [
                "checkout-api 存在 CrashLoopBackOff",
                "checkout-api Service endpoints 为空",
                "worker-1 节点存在 MemoryPressure",
            ],
        }

    def list_nodes(self) -> list[K8sNodeSummary]:
        """返回稳定节点健康数据"""
        return [
            K8sNodeSummary(
                name="demo-control-plane",
                ready=True,
                roles=["control-plane"],
                cpu_capacity="4",
                memory_capacity="8Gi",
                cpu_allocatable="3800m",
                memory_allocatable="7600Mi",
                conditions=[K8sCondition(type="Ready", status="True", reason="KubeletReady")],
            ),
            K8sNodeSummary(
                name="demo-worker-1",
                ready=True,
                roles=["worker"],
                cpu_capacity="4",
                memory_capacity="8Gi",
                cpu_allocatable="3900m",
                memory_allocatable="7800Mi",
                conditions=[
                    K8sCondition(type="Ready", status="True", reason="KubeletReady"),
                    K8sCondition(
                        type="MemoryPressure",
                        status="True",
                        reason="KubeletHasInsufficientMemory",
                        message="节点可用内存低于驱逐阈值",
                    ),
                ],
            ),
            K8sNodeSummary(
                name="demo-worker-2",
                ready=True,
                roles=["worker"],
                cpu_capacity="4",
                memory_capacity="8Gi",
                cpu_allocatable="3900m",
                memory_allocatable="7800Mi",
                conditions=[K8sCondition(type="Ready", status="True", reason="KubeletReady")],
            ),
        ]

    def list_pods(self, namespace: str = "default", workload: str = "") -> list[K8sPodSummary]:
        """返回稳定 Pod 健康数据"""
        target_namespace = namespace or "prod"
        pods = [
            K8sPodSummary(
                name="checkout-api-6f7d9f9c5b-x2k7m",
                namespace=target_namespace,
                workload="checkout-api",
                phase="Running",
                node_name="demo-worker-1",
                restart_count=17,
                ready=False,
                reason="CrashLoopBackOff",
                message="容器启动后因 DB_CONN_TIMEOUT 退出",
                container_images=["registry.local/checkout-api:v1.8.3"],
            ),
            K8sPodSummary(
                name="checkout-api-6f7d9f9c5b-p8r4q",
                namespace=target_namespace,
                workload="checkout-api",
                phase="Running",
                node_name="demo-worker-1",
                restart_count=13,
                ready=False,
                reason="CrashLoopBackOff",
                message="Readiness probe 连续失败",
                container_images=["registry.local/checkout-api:v1.8.3"],
            ),
            K8sPodSummary(
                name="payment-api-788bccd65f-vn2lf",
                namespace=target_namespace,
                workload="payment-api",
                phase="Running",
                node_name="demo-worker-2",
                restart_count=0,
                ready=True,
                container_images=["registry.local/payment-api:v2.1.0"],
            ),
        ]
        if workload:
            return [pod for pod in pods if workload in pod.workload or workload in pod.name]
        return pods

    def list_events(self, namespace: str = "default", workload: str = "") -> list[K8sEventSummary]:
        """返回稳定事件数据"""
        target_namespace = namespace or "prod"
        events = [
            K8sEventSummary(
                namespace=target_namespace,
                involved_object="pod/checkout-api-6f7d9f9c5b-x2k7m",
                reason="BackOff",
                message="Back-off restarting failed container checkout-api",
                type="Warning",
                count=18,
                last_timestamp="2026-06-02T09:35:00Z",
            ),
            K8sEventSummary(
                namespace=target_namespace,
                involved_object="pod/checkout-api-6f7d9f9c5b-p8r4q",
                reason="Unhealthy",
                message="Readiness probe failed: dial tcp 10.1.2.33:8080: connect: connection refused",
                type="Warning",
                count=12,
                last_timestamp="2026-06-02T09:34:30Z",
            ),
            K8sEventSummary(
                namespace=target_namespace,
                involved_object="node/demo-worker-1",
                reason="NodeHasInsufficientMemory",
                message="Node demo-worker-1 status is now: NodeHasInsufficientMemory",
                type="Warning",
                count=4,
                last_timestamp="2026-06-02T09:33:20Z",
            ),
        ]
        if workload:
            return [
                event
                for event in events
                if workload in event.involved_object or workload in event.message
            ]
        return events

    def resource_usage(
        self, namespace: str = "default", workload: str = ""
    ) -> list[K8sMetricPoint]:
        """返回稳定资源使用数据"""
        target_namespace = namespace or "prod"
        return [
            K8sMetricPoint(
                kind="node",
                name="demo-worker-1",
                cpu="2650m",
                memory="7420Mi",
                note="内存接近可分配上限",
            ),
            K8sMetricPoint(kind="node", name="demo-worker-2", cpu="940m", memory="3100Mi"),
            K8sMetricPoint(
                kind="workload",
                namespace=target_namespace,
                name=workload or "checkout-api",
                cpu="180m",
                memory="512Mi",
                note="Pod 重启导致业务不可用，资源不是直接瓶颈",
            ),
        ]

    def service_endpoints(
        self, namespace: str = "default", service_name: str = ""
    ) -> dict[str, Any]:
        """返回稳定 Service/Endpoint 检查数据"""
        return {
            "namespace": namespace or "prod",
            "service_name": service_name or "checkout-api",
            "service_exists": True,
            "endpoint_count": 0,
            "ready_addresses": [],
            "not_ready_addresses": ["10.244.1.23", "10.244.1.24"],
            "message": "Service 存在，但没有 Ready Endpoint，流量无法转发到健康 Pod",
        }


class RealKubernetesProvider(KubernetesProvider):
    """真实 Kubernetes API 只读 Provider"""

    mode = "real"

    def __init__(self) -> None:
        """延迟加载 Kubernetes client，避免无依赖环境导入失败"""
        self._ready = False
        self._message = "未初始化"
        self._core_v1 = None
        self._apps_v1 = None
        self._init_client()

    def _init_client(self) -> None:
        """初始化 Kubernetes API client"""
        try:
            from kubernetes import client, config as k8s_config
            from kubernetes.config.config_exception import ConfigException

            kubeconfig = config.kubeconfig or os.getenv("KUBECONFIG")
            try:
                if kubeconfig:
                    k8s_config.load_kube_config(config_file=kubeconfig, context=config.k8s_context)
                    self._message = f"已使用 kubeconfig 连接集群: {kubeconfig}"
                else:
                    k8s_config.load_kube_config(context=config.k8s_context)
                    self._message = "已使用默认 kubeconfig 连接集群"
            except ConfigException:
                k8s_config.load_incluster_config()
                self._message = "已使用 in-cluster 配置连接集群"

            self._core_v1 = client.CoreV1Api()
            self._apps_v1 = client.AppsV1Api()
            self._ready = True
        except Exception as exc:
            self._ready = False
            self._message = f"真实 Kubernetes Provider 不可用: {exc}"
            logger.warning(self._message)

    def status(self) -> ProviderStatus:
        """返回真实 Provider 状态"""
        return ProviderStatus(
            name="real-kubernetes-provider",
            mode=self.mode,
            ready=self._ready,
            message=self._message,
        )

    def _require_core(self):
        """获取 CoreV1Api"""
        if not self._ready or self._core_v1 is None:
            raise RuntimeError(self._message)
        return self._core_v1

    def cluster_overview(self) -> dict[str, Any]:
        """获取真实集群概览"""
        core = self._require_core()
        nodes = core.list_node().items
        pods = core.list_pod_for_all_namespaces().items
        unhealthy = [
            pod
            for pod in pods
            if pod.status.phase not in {"Running", "Succeeded"}
            or any(
                (status.restart_count or 0) > 0 for status in (pod.status.container_statuses or [])
            )
        ]
        return {
            "cluster": config.k8s_context or "current",
            "provider": self.mode,
            "node_count": len(nodes),
            "namespace_count": len(core.list_namespace().items),
            "pod_count": len(pods),
            "unhealthy_pod_count": len(unhealthy),
        }

    def list_nodes(self) -> list[K8sNodeSummary]:
        """获取真实节点健康数据"""
        core = self._require_core()
        summaries: list[K8sNodeSummary] = []
        for node in core.list_node().items:
            labels = node.metadata.labels or {}
            roles = [
                key.replace("node-role.kubernetes.io/", "")
                for key in labels
                if key.startswith("node-role.kubernetes.io/")
            ]
            conditions = [
                K8sCondition(
                    type=condition.type or "",
                    status=condition.status or "",
                    reason=condition.reason or "",
                    message=condition.message or "",
                )
                for condition in (node.status.conditions or [])
            ]
            ready = any(
                condition.type == "Ready" and condition.status == "True" for condition in conditions
            )
            capacity = node.status.capacity or {}
            allocatable = node.status.allocatable or {}
            summaries.append(
                K8sNodeSummary(
                    name=node.metadata.name or "",
                    ready=ready,
                    roles=roles or ["worker"],
                    cpu_capacity=str(capacity.get("cpu", "")),
                    memory_capacity=str(capacity.get("memory", "")),
                    cpu_allocatable=str(allocatable.get("cpu", "")),
                    memory_allocatable=str(allocatable.get("memory", "")),
                    conditions=conditions,
                )
            )
        return summaries

    def list_pods(self, namespace: str = "default", workload: str = "") -> list[K8sPodSummary]:
        """获取真实 Pod 健康数据"""
        core = self._require_core()
        pods = core.list_namespaced_pod(namespace=namespace or config.k8s_namespace).items
        summaries: list[K8sPodSummary] = []
        for pod in pods:
            owner_refs = pod.metadata.owner_references or []
            owner = owner_refs[0].name if owner_refs else ""
            name = pod.metadata.name or ""
            if workload and workload not in name and workload not in owner:
                continue
            statuses = pod.status.container_statuses or []
            restart_count = sum(status.restart_count or 0 for status in statuses)
            ready = bool(statuses) and all(bool(status.ready) for status in statuses)
            reason = pod.status.reason or ""
            message = pod.status.message or ""
            waiting_reasons = [
                status.state.waiting.reason
                for status in statuses
                if status.state and status.state.waiting and status.state.waiting.reason
            ]
            if waiting_reasons:
                reason = waiting_reasons[0]
            summaries.append(
                K8sPodSummary(
                    name=name,
                    namespace=pod.metadata.namespace or namespace,
                    workload=owner,
                    phase=pod.status.phase or "",
                    node_name=pod.spec.node_name or "",
                    restart_count=restart_count,
                    ready=ready,
                    reason=reason,
                    message=message,
                    container_images=[container.image for container in (pod.spec.containers or [])],
                )
            )
        return summaries

    def list_events(self, namespace: str = "default", workload: str = "") -> list[K8sEventSummary]:
        """获取真实事件数据"""
        core = self._require_core()
        events = core.list_namespaced_event(namespace=namespace or config.k8s_namespace).items
        summaries: list[K8sEventSummary] = []
        for event in events:
            involved = f"{event.involved_object.kind}/{event.involved_object.name}"
            if workload and workload not in involved and workload not in (event.message or ""):
                continue
            last_ts = event.last_timestamp or event.event_time or event.first_timestamp
            summaries.append(
                K8sEventSummary(
                    namespace=event.metadata.namespace or namespace,
                    involved_object=involved,
                    reason=event.reason or "",
                    message=event.message or "",
                    type=event.type or "Normal",
                    count=event.count or 1,
                    last_timestamp=last_ts.isoformat() if last_ts else "",
                )
            )
        return summaries[-50:]

    def resource_usage(
        self, namespace: str = "default", workload: str = ""
    ) -> list[K8sMetricPoint]:
        """获取资源使用数据。

        Metrics Server 并非所有集群都安装；这里先返回可解释的只读提示。
        """
        pods = self.list_pods(namespace=namespace, workload=workload)
        return [
            K8sMetricPoint(
                kind="workload",
                namespace=namespace,
                name=workload or "all",
                note=f"已发现 {len(pods)} 个相关 Pod；如需实时 CPU/内存，请在集群安装 metrics-server。",
            )
        ]

    def service_endpoints(
        self, namespace: str = "default", service_name: str = ""
    ) -> dict[str, Any]:
        """获取真实 Service/Endpoint 检查结果"""
        core = self._require_core()
        ns = namespace or config.k8s_namespace
        svc_name = service_name
        if not svc_name:
            return {
                "namespace": ns,
                "service_name": "",
                "service_exists": False,
                "message": "未提供 service_name",
            }
        try:
            service = core.read_namespaced_service(name=svc_name, namespace=ns)
            endpoints = core.read_namespaced_endpoints(name=svc_name, namespace=ns)
        except Exception as exc:
            return {
                "namespace": ns,
                "service_name": svc_name,
                "service_exists": False,
                "message": f"Service 或 Endpoint 不可读: {exc}",
            }
        ready_addresses = []
        not_ready_addresses = []
        for subset in endpoints.subsets or []:
            ready_addresses.extend([addr.ip for addr in (subset.addresses or []) if addr.ip])
            not_ready_addresses.extend(
                [addr.ip for addr in (subset.not_ready_addresses or []) if addr.ip]
            )
        return {
            "namespace": ns,
            "service_name": service.metadata.name,
            "service_exists": True,
            "endpoint_count": len(ready_addresses),
            "ready_addresses": ready_addresses,
            "not_ready_addresses": not_ready_addresses,
            "message": "Service Endpoint 检查完成",
        }


_provider_cache: dict[str, KubernetesProvider] = {}


def get_kubernetes_provider(mode: str | None = None) -> KubernetesProvider:
    """按模式获取 Kubernetes Provider。

    auto 模式优先真实集群；不可用时降级为 Demo Provider，确保 Linux 演示可运行。

    注意：real 模式不缓存失败的实例，每次调用都重新尝试初始化，
    避免因临时网络问题导致永久降级。但成功连接的实例会被缓存复用，
    避免反复加载 kubeconfig 和创建 API 客户端。
    """
    selected_mode = (mode or config.k8s_provider_mode or "auto").lower()
    if selected_mode == "demo":
        if "demo" not in _provider_cache:
            _provider_cache["demo"] = DemoKubernetesProvider()
        return _provider_cache["demo"]
    if selected_mode == "real":
        if "real" not in _provider_cache or not _provider_cache["real"].status().ready:
            _provider_cache["real"] = RealKubernetesProvider()
        return _provider_cache["real"]

    # auto 模式：优先使用真实集群，成功后缓存；不可用时降级
    if "auto-cached-real" in _provider_cache and _provider_cache["auto-cached-real"].status().ready:
        return _provider_cache["auto-cached-real"]

    real_provider = RealKubernetesProvider()
    if real_provider.status().ready:
        _provider_cache["auto-cached-real"] = real_provider
        return real_provider
    logger.info("真实 Kubernetes 不可用，自动降级到 Demo Provider")
    if "demo" not in _provider_cache:
        _provider_cache["demo"] = DemoKubernetesProvider()
    return _provider_cache["demo"]

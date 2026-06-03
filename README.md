# Kubernetes AIOps Agent

> 基于 LangChain、MCP、Chroma、Kubernetes 和飞书的告警驱动运维助手 Agent。

## 核心能力

- Kubernetes 只读诊断：节点健康、异常 Pod、事件、资源摘要、Service Endpoint。
- MCP 工具封装：`mcp_servers/kubernetes_server.py` 暴露 Kubernetes 只读工具。
- Chroma 知识库：本地持久化运维手册和 Kubernetes 故障案例。
- 结构化 Agent：按 `incident -> runbook -> evidence -> hypothesis -> action_plan -> report` 输出证据链。
- 飞书集成：支持 URL verification、消息回调、文本回复和 webhook 推送。
- Linux 部署：支持 Docker Compose；可选用 kind 创建演示集群。

## 快速启动

```bash
uv sync --extra dev

# Demo Provider 模式，无需真实 Kubernetes 集群
K8S_PROVIDER_MODE=demo make docker-up

# 访问
curl http://127.0.0.1:9900/health
curl http://127.0.0.1:9900/ready
```

## Kubernetes 诊断接口

```bash
curl -N http://127.0.0.1:9900/api/aiops/diagnose \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-1",
    "mode": "demo",
    "cluster": "demo-kind",
    "namespace": "prod",
    "workload": "checkout-api",
    "question": "checkout-api 持续重启，请诊断根因",
    "include_actions": true,
    "alert": {
      "name": "KubePodCrashLooping",
      "severity": "critical",
      "summary": "checkout-api Pod CrashLoopBackOff",
      "labels": {"service": "checkout-api"}
    }
  }'
```

SSE 事件类型：`status`、`incident`、`evidence`、`hypothesis`、`action_plan`、`report`、`complete`、`error`。

## 真实集群接入

```bash
export K8S_PROVIDER_MODE=real
export KUBECONFIG_HOST_PATH="$HOME/.kube/config"
export KUBECONFIG=/home/aiops/.kube/config
make docker-up
```

Agent 默认只读诊断。所有写操作只作为待审批建议输出，包含命令、风险等级、证据引用和回滚方式。

## kind 演示

```bash
bash scripts/kind_bootstrap.sh
K8S_PROVIDER_MODE=real K8S_NAMESPACE=aiops-demo make docker-up
bash scripts/smoke_aiops_kind.sh
```

## 飞书配置

`.env` 中按需配置：

```bash
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
FEISHU_WEBHOOK_URL=
FEISHU_WEBHOOK_SECRET=
```

事件回调地址：`POST /api/feishu/events`。

## 常用命令

```bash
make docker-up
make docker-down
make docker-logs
make docker-test

make lint
make test
```


#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${KIND_CLUSTER_NAME:-aiops-demo}"
NAMESPACE="${K8S_NAMESPACE:-aiops-demo}"

command -v kind >/dev/null || { echo "kind 未安装，请先安装 kind"; exit 1; }
command -v kubectl >/dev/null || { echo "kubectl 未安装，请先安装 kubectl"; exit 1; }

if ! kind get clusters | grep -qx "$CLUSTER_NAME"; then
  echo "==> 创建 kind 集群: $CLUSTER_NAME"
  kind create cluster --name "$CLUSTER_NAME"
else
  echo "==> kind 集群已存在: $CLUSTER_NAME"
fi

echo "==> 创建演示 namespace: $NAMESPACE"
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

echo "==> 部署 CrashLoopBackOff 演示工作负载"
kubectl -n "$NAMESPACE" apply -f - <<'YAML'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-api
  labels:
    app: checkout-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: checkout-api
  template:
    metadata:
      labels:
        app: checkout-api
    spec:
      containers:
        - name: checkout-api
          image: busybox:1.36
          command: ["sh", "-c", "echo DB_CONN_TIMEOUT; exit 1"]
---
apiVersion: v1
kind: Service
metadata:
  name: checkout-api
spec:
  selector:
    app: checkout-api
  ports:
    - port: 80
      targetPort: 8080
YAML

echo "==> 等待故障样例进入可诊断状态"
sleep 10
kubectl -n "$NAMESPACE" get pods,svc
echo "==> kind 演示环境完成"

#!/usr/bin/env bash
set -euo pipefail

APP_URL="${APP_URL:-http://127.0.0.1:9900}"
NAMESPACE="${K8S_NAMESPACE:-aiops-demo}"

echo "==> 检查 AIOps Agent 就绪状态"
curl -fsS "$APP_URL/ready" >/dev/null

echo "==> 触发 Kubernetes AIOps 诊断"
curl -fsS -N "$APP_URL/api/aiops/diagnose" \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\":\"smoke-kind\",
    \"mode\":\"auto\",
    \"cluster\":\"kind-aiops-demo\",
    \"namespace\":\"$NAMESPACE\",
    \"workload\":\"checkout-api\",
    \"question\":\"checkout-api 持续重启，请诊断根因并给出可审批处置建议\",
    \"include_actions\":true,
    \"alert\":{\"name\":\"KubePodCrashLooping\",\"severity\":\"critical\",\"summary\":\"checkout-api Pod CrashLoopBackOff\",\"labels\":{\"service\":\"checkout-api\"}}
  }" | tee /tmp/aiops-smoke.out

grep -q "diagnosis_complete" /tmp/aiops-smoke.out
grep -q "evidence" /tmp/aiops-smoke.out
grep -q "action_plan" /tmp/aiops-smoke.out
echo "==> AIOps smoke test 通过"

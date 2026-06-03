#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE="${DOCKER_COMPOSE:-docker compose}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
APP_PORT="${APP_PORT:-9900}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:${APP_PORT}/ready}"
DIAGNOSE_URL="${DIAGNOSE_URL:-http://127.0.0.1:${APP_PORT}/api/aiops/diagnose}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-90}"

echo "==> 检查 Docker Compose 配置"
$COMPOSE -f "$COMPOSE_FILE" config >/dev/null

echo "==> 构建 Linux 容器镜像"
$COMPOSE -f "$COMPOSE_FILE" build

if [[ "${SKIP_UP:-0}" == "1" ]]; then
  echo "==> 已按 SKIP_UP=1 跳过启动验证"
  exit 0
fi

echo "==> 启动 Linux 容器栈"
$COMPOSE -f "$COMPOSE_FILE" up -d

cleanup() {
  if [[ "${KEEP_RUNNING:-0}" != "1" ]]; then
    echo "==> 停止 Linux 容器栈"
    $COMPOSE -f "$COMPOSE_FILE" down
  fi
}
trap cleanup EXIT

echo "==> 等待就绪检查: $HEALTH_URL"
for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  if curl -fsS "$HEALTH_URL" >/dev/null; then
    echo "==> Linux 部署就绪检查通过"
    ready=1
    break
  fi
  printf '等待中 [%s/%s]\n' "$attempt" "$MAX_ATTEMPTS"
  sleep 2
done

if [[ "${ready:-0}" != "1" ]]; then
  echo "==> 就绪检查超时，输出最近日志"
  $COMPOSE -f "$COMPOSE_FILE" logs --tail=120 app kubernetes-mcp
  exit 1
fi

echo "==> 调用 Demo AIOps SSE 诊断"
tmp_response="$(mktemp)"
curl -fsS -N "$DIAGNOSE_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "linux-smoke",
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
  }' > "$tmp_response"

echo "==> 校验 Demo 诊断关键事件"
for pattern in \
  "incident_normalized" \
  "evidence_collected" \
  "actions_created" \
  "report_created" \
  "diagnosis_complete" \
  "trace_id" \
  "risk_summary" \
  "evidence_coverage" \
  "next_steps"; do
  if ! grep -q "$pattern" "$tmp_response"; then
    echo "==> 缺少关键诊断输出: $pattern"
    cat "$tmp_response"
    rm -f "$tmp_response"
    exit 1
  fi
done

rm -f "$tmp_response"
echo "==> Linux 部署 smoke 验证通过"

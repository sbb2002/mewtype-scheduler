#!/usr/bin/env bash
set -euo pipefail

source deploy/env.sh

echo "=== 서비스 URL 조회 ==="
URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region "$GCP_LOCATION" \
  --format='value(status.url)')

# 스케줄러 잡 생성/갱신 헬퍼.
#   $1 = 잡 이름, $2 = cron, $3 = time-zone, $4 = message-body(JSON)
# --max-retry-attempts: Cloud Run concurrency=1 이라 다른 요청 처리 중이면 429 가능 → 재시도.
upsert_job () {
  local name="$1" cron="$2" tz="$3" body="$4" verb=create
  if gcloud scheduler jobs describe "$name" --location="$GCP_LOCATION" &>/dev/null; then
    verb=update
  fi
  echo "${verb}: $name"
  gcloud scheduler jobs "$verb" http "$name" \
    --location="$GCP_LOCATION" \
    --schedule="$cron" \
    --time-zone="$tz" \
    --uri="$URL/tick" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body="$body" \
    --oidc-service-account-email="$INVOKER_SA" \
    --oidc-token-audience="$URL" \
    --max-retry-attempts=3 \
    --min-backoff=30s \
    --max-backoff=300s
}

echo "=== Baseline 스케줄러 (JST 06:00) ==="
upsert_job mewtype-baseline "0 6 * * *" "Asia/Tokyo" '{"mode":"baseline"}'

echo "=== Light 안전망 (3시간 간격 UTC) ==="
upsert_job mewtype-light "0 */3 * * *" "Etc/UTC" '{"mode":"light"}'

echo "=== 스케줄러 설정 완료 ==="

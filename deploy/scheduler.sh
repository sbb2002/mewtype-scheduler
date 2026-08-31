#!/usr/bin/env bash
set -euo pipefail

source deploy/env.sh

echo "=== 서비스 URL 조회 ==="
URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region "$GCP_LOCATION" \
  --format='value(status.url)')

echo "=== Baseline 스케줄러 (JST 06:00) ==="
if gcloud scheduler jobs describe mewtype-baseline --location="$GCP_LOCATION" &>/dev/null; then
  echo "업데이트 중: mewtype-baseline"
  gcloud scheduler jobs update http mewtype-baseline \
    --location="$GCP_LOCATION" \
    --schedule="0 6 * * *" \
    --time-zone="Asia/Tokyo" \
    --uri="$URL/tick" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"mode":"baseline"}' \
    --oidc-service-account-email="$INVOKER_SA" \
    --oidc-token-audience="$URL"
else
  echo "생성 중: mewtype-baseline"
  gcloud scheduler jobs create http mewtype-baseline \
    --location="$GCP_LOCATION" \
    --schedule="0 6 * * *" \
    --time-zone="Asia/Tokyo" \
    --uri="$URL/tick" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"mode":"baseline"}' \
    --oidc-service-account-email="$INVOKER_SA" \
    --oidc-token-audience="$URL"
fi

echo "=== Light 안전망 (3시간 간격 UTC) ==="
if gcloud scheduler jobs describe mewtype-light --location="$GCP_LOCATION" &>/dev/null; then
  echo "업데이트 중: mewtype-light"
  gcloud scheduler jobs update http mewtype-light \
    --location="$GCP_LOCATION" \
    --schedule="0 */3 * * *" \
    --time-zone="Etc/UTC" \
    --uri="$URL/tick" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"mode":"light"}' \
    --oidc-service-account-email="$INVOKER_SA" \
    --oidc-token-audience="$URL"
else
  echo "생성 중: mewtype-light"
  gcloud scheduler jobs create http mewtype-light \
    --location="$GCP_LOCATION" \
    --schedule="0 */3 * * *" \
    --time-zone="Etc/UTC" \
    --uri="$URL/tick" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"mode":"light"}' \
    --oidc-service-account-email="$INVOKER_SA" \
    --oidc-token-audience="$URL"
fi

echo "=== 스케줄러 설정 완료 ==="

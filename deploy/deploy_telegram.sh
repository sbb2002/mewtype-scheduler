#!/usr/bin/env bash
set -euo pipefail

source deploy/env.sh

echo "=== mewtype-telegram 서비스 URL 조회 ==="
MAIN_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$GCP_LOCATION" --format='value(status.url)')

echo "=== mewtype-telegram 배포 (webhook 서비스) ==="
# INVOKER_SA 로 실행한다. /resume 이 메인 /tick 을 OIDC 로 호출할 때 메인의
# oidc.verify_request 가 caller email == INVOKER_SA 를 요구하기 때문.
# --command/--args: 값이 '-' 로 시작하면 gcloud 가 다음 플래그로 오인하므로 '=' 로 붙인다.
gcloud run deploy mewtype-telegram \
  --source . --region "$GCP_LOCATION" \
  --allow-unauthenticated \
  --service-account "$INVOKER_SA" \
  --command=gunicorn \
  --args="--bind=0.0.0.0:8080,--workers=1,--threads=4,--timeout=60,src.backend.telegram_app:app" \
  --set-secrets "GITHUB_TOKEN=GITHUB_TOKEN:latest,TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,TELEGRAM_WEBHOOK_SECRET=TELEGRAM_WEBHOOK_SECRET:latest" \
  --set-env-vars "GITHUB_REPO=$GITHUB_REPO,DATA_BRANCH=$DATA_BRANCH,TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID,MAIN_SERVICE_URL=$MAIN_URL,ALLOW_UNAUTH=1"

echo "=== 메인서비스 invoker 권한 부여 (telegram_app 의 /resume heal 호출용) ==="
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --region "$GCP_LOCATION" \
  --member "serviceAccount:$INVOKER_SA" \
  --role roles/run.invoker \
  --quiet 2>/dev/null || true

echo "=== mewtype-telegram 배포 완료 ==="

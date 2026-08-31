#!/usr/bin/env bash
set -euo pipefail

source deploy/env.sh

echo "=== Cloud Run 배포 ==="
gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region "$GCP_LOCATION" \
  --no-allow-unauthenticated \
  --service-account "$RUNTIME_SA" \
  --set-secrets "YOUTUBE_API_KEY=YOUTUBE_API_KEY:latest,GITHUB_TOKEN=GITHUB_TOKEN:latest,TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest" \
  --set-env-vars "GITHUB_REPO=$GITHUB_REPO,DATA_BRANCH=$DATA_BRANCH,GCP_PROJECT=$GCP_PROJECT,GCP_LOCATION=$GCP_LOCATION,TASKS_QUEUE=$TASKS_QUEUE,INVOKER_SA=$INVOKER_SA,TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID,HEALTHCHECK_URL=$HEALTHCHECK_URL,SERVICE_URL=https://placeholder.invalid"
# SERVICE_URL 은 배포 후 실제 URL 을 알 수 있으므로 일단 placeholder 로 부팅시키고 아래에서 교체한다.

echo "=== 서비스 URL 조회 ==="
URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region "$GCP_LOCATION" \
  --format='value(status.url)')

echo "=== SERVICE_URL 환경변수 재설정 ==="
gcloud run services update "$SERVICE_NAME" \
  --region "$GCP_LOCATION" \
  --update-env-vars "SERVICE_URL=$URL"

echo "=== Invoker 권한 부여 ==="
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --region "$GCP_LOCATION" \
  --member "serviceAccount:$INVOKER_SA" \
  --role roles/run.invoker \
  --quiet 2>/dev/null || true

echo "=== 배포 완료 ==="
echo "SERVICE_URL=$URL"

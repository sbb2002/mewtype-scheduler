#!/usr/bin/env bash
set -euo pipefail

source deploy/env.sh

# webhook 해제 모드
if [[ "${1:-}" == "delete" ]]; then
  echo "=== Telegram webhook 해제 중 ==="
  curl -fsS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook"
  echo
  echo "=== webhook 해제 완료 ==="
  exit 0
fi

echo "=== mewtype-telegram 서비스 URL 조회 ==="
TG_URL=$(gcloud run services describe mewtype-telegram --region "$GCP_LOCATION" --format='value(status.url)')

echo "=== Telegram webhook 등록 ==="
curl -fsS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=${TG_URL}/telegram" \
  -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}" \
  -d "allowed_updates=[\"message\"]"
echo

echo "=== webhook 등록 완료 ==="
echo "URL: ${TG_URL}/telegram"

#!/usr/bin/env bash
set -euo pipefail

source deploy/env.sh

echo "=== 서비스 URL 조회 ==="
URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region "$GCP_LOCATION" \
  --format='value(status.url)')

# 스케줄러 잡 생성/갱신 헬퍼.
#   $1 = 잡 이름, $2 = cron, $3 = time-zone, $4 = message-body(JSON), $5 = 엔드포인트 경로(기본 /tick)
# --max-retry-attempts: Cloud Run concurrency=1 이라 다른 요청 처리 중이면 429 가능 → 재시도.
upsert_job () {
  local name="$1" cron="$2" tz="$3" body="$4" path="${5:-/tick}" verb=create
  if gcloud scheduler jobs describe "$name" --location="$GCP_LOCATION" &>/dev/null; then
    verb=update
  fi
  # gcloud 신버전: create 는 --headers=, update 는 --update-headers= (--headers 미지원).
  local hdr_flag="--headers=Content-Type=application/json"
  [ "$verb" = update ] && hdr_flag="--update-headers=Content-Type=application/json"
  echo "${verb}: $name"
  gcloud scheduler jobs "$verb" http "$name" \
    --location="$GCP_LOCATION" \
    --schedule="$cron" \
    --time-zone="$tz" \
    --uri="$URL$path" \
    --http-method=POST \
    "$hdr_flag" \
    --message-body="$body" \
    --oidc-service-account-email="$INVOKER_SA" \
    --oidc-token-audience="$URL" \
    --max-retry-attempts=3 \
    --min-backoff=30s \
    --max-backoff=300s
}

echo "=== Baseline 스케줄러 (JST 06:00) ==="
upsert_job mewtype-baseline "0 6 * * *" "Asia/Tokyo" '{"mode":"baseline"}'

echo "=== Light 안전망 (10분 간격 UTC) ==="
upsert_job mewtype-light "*/10 * * * *" "Etc/UTC" '{"mode":"light"}'

# baseline(mewtype-baseline)과 같은 "0 6 * * *"였다가, 두 Scheduler 잡이 완전히 동시에
# 발사되면서 Cloud Run(concurrency=1·max-instances=1, 직렬화)에 어느 쪽이 먼저 들어갈지가
# 요청 도착 순서에 달린 레이스가 됐다 — /monitor가 /tick보다 먼저 처리된 날은 baseline
# tick이 아직 monitor_log에 그날 첫 이벤트를 쓰기 전이라 리포트가 완전히 빈 채로 DM 발송됨
# (실측 2026-09-16: mewtype-backend 로그상 인스턴스 콜드스타트 후 tick 처리가 6초 지연 시작
# — 그 사이 /monitor가 먼저 끝났다고 볼 수 있음). 06:10으로 늦춰 baseline tick(보통 20초
# 안팎 소요)이 이벤트를 다 쓴 뒤 monitor가 그 날짜 파일을 읽도록 순서를 강제한다.
echo "=== Monitor (1일 1회 KST 06:10 — baseline tick 완료 후) — control.json monitor_auto 켜져 있을 때만 실제 리포트 생성+DM ==="
upsert_job mewtype-monitor "10 6 * * *" "Asia/Seoul" '{}' "/monitor"

echo "=== 스케줄러 설정 완료 ==="

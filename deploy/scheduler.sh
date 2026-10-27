#!/usr/bin/env bash
set -euo pipefail

# (self-reply D10) 스테이징에는 Scheduler 잡을 만들지 않는다 — 스테이징 시험은 수동 호출로만. 아무것도 하지 않고 끝낸다.
if [ "${STAGE:-0}" = 1 ]; then
  echo "STAGE=1 — 스테이징은 Scheduler 잡을 만들지 않는다(운영 잡 이름 mewtype-* 을 스테이징 URL 로 덮어쓰지 않게). 아무것도 안 함."
  exit 0
fi

# (self-reply) 일일 묶음 잡(KST 06:00 · 06:10 · 06:20 의 예약)이 도는 창에는 잡을 바꾸지 않는다 — 두 벌이 겹치면 monitor DM 이 두 번 간다.
_HHMM=$(TZ=Asia/Seoul date +%H%M)
if [ "$((10#$_HHMM))" -ge 550 ] && [ "$((10#$_HHMM))" -le 630 ]; then
  echo "거부: 지금 KST ${_HHMM} — 05:50~06:30 에는 Scheduler 잡을 바꾸지 않는다(일일 묶음 잡 · 06:10 · 06:20 예약과 겹침). 06:30 이후에 다시 실행." >&2
  exit 1
fi

source deploy/env.sh
# (v4) STAGE=1 이면 스테이징 서비스 · 큐 · 브랜치로 덮어쓴다 (deploy/env.stage.sh) — 위에서 STAGE=1 은 이미 빠져나갔다
if [ "${STAGE:-0}" = 1 ]; then source deploy/env.stage.sh; fi

echo "=== 서비스 URL 조회 ==="
URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region "$GCP_LOCATION" \
  --format='value(status.url)')
# (self-reply) 접수 서비스(mewtype-telegram) 주소 — 상시 조사 `/gap-check` 는 접수 서비스로 간다
TG_URL=$(gcloud run services describe "${TELEGRAM_SERVICE:-mewtype-telegram}" \
  --region "$GCP_LOCATION" \
  --format='value(status.url)')

# 스케줄러 잡 생성/갱신 헬퍼.
#   $1 = 잡 이름, $2 = cron, $3 = time-zone, $4 = message-body(JSON), $5 = 엔드포인트 경로(기본 /tick),
#   $6 = 호출할 서비스 주소(기본 쓰기 서비스 $URL), $7 = OIDC audience(기본 = $6)
# --max-retry-attempts: Cloud Run concurrency=1 이라 다른 요청 처리 중이면 429 가능 → 재시도.
upsert_job () {
  local name="$1" cron="$2" tz="$3" body="$4" path="${5:-/tick}" base="${6:-$URL}" aud="${7:-${6:-$URL}}" verb=create
  if gcloud scheduler jobs describe "$name" --location="$GCP_LOCATION" &>/dev/null; then
    verb=update
  fi
  # gcloud 신버전: create 는 --headers=, update 는 --update-headers= (--headers 미지원).
  local hdr_flag="--headers=Content-Type=application/json"
  [ "$verb" = update ] && hdr_flag="--update-headers=Content-Type=application/json"
  echo "${verb}: $name → ${base}${path}"
  gcloud scheduler jobs "$verb" http "$name" \
    --location="$GCP_LOCATION" \
    --schedule="$cron" \
    --time-zone="$tz" \
    --uri="${base}${path}" \
    --http-method=POST \
    "$hdr_flag" \
    --message-body="$body" \
    --oidc-service-account-email="$INVOKER_SA" \
    --oidc-token-audience="$aud" \
    --max-retry-attempts=3 \
    --min-backoff=30s \
    --max-backoff=300s
}

echo "=== Light 안전망 (10분 간격 UTC) ==="
upsert_job mewtype-light "*/10 * * * *" "Etc/UTC" '{"mode":"light"}'

# (self-reply D6 · 명세 §4-6 · §5-1) 일일 묶음 잡 — 옛 잡 3개(baseline 06:00 · monitor 06:10 · websub-renew 06:20)를 대신한다.
#   쓰기 서비스 /daily 가 그날 06:10 · 06:20 의 /monitor · /websub-renew 를 Cloud Tasks(DAILY_QUEUE)에 먼저 예약하고, 그다음 baseline tick 을 돈다.
#   그래서 06:10 · 06:20 이 Scheduler 가 아니라 Cloud Tasks 시각으로 돈다(baseline 과 monitor 의 순서는 그대로 보장).
echo "=== 일일 묶음 잡 (매일 KST 06:00 — baseline + 06:10 monitor + 06:20 websub-renew 예약) ==="
upsert_job mewtype-daily "0 6 * * *" "Asia/Seoul" '{}' "/daily" "$URL" "$URL"

# (self-reply D6) 상시 조사 — 매분 접수 서비스 /gap-check (OIDC audience = 접수 서비스 주소, 발급자 = INVOKER_SA).
echo "=== 상시 조사 (매분 — 접수 서비스 /gap-check) ==="
upsert_job mewtype-gapcheck "* * * * *" "Etc/UTC" '{}' "/gap-check" "$TG_URL" "$TG_URL"

# 새 잡을 다 만든 뒤에 옛 잡을 지운다 — 같은 날 옛 잡과 새 잡이 함께 돌아 monitor DM 이 두 번 가는 일을 막는다(§5-1).
echo "=== 옛 잡 삭제 (mewtype-baseline · mewtype-monitor · mewtype-websub-renew — 일일 묶음 잡으로 대체) ==="
for old in mewtype-baseline mewtype-monitor mewtype-websub-renew; do
  if gcloud scheduler jobs describe "$old" --location="$GCP_LOCATION" &>/dev/null; then
    echo "delete: $old"
    gcloud scheduler jobs delete "$old" --location="$GCP_LOCATION" --quiet
  else
    echo "없음(건너뜀): $old"
  fi
done

echo "=== 스케줄러 설정 완료 (light · daily · gapcheck 3개) ==="

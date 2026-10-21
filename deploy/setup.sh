#!/usr/bin/env bash
set -euo pipefail

source deploy/env.sh

echo "=== GCP 프로젝트 설정 ==="
gcloud config set project "$GCP_PROJECT"

echo "=== API 활성화 ==="
gcloud services enable \
  run.googleapis.com \
  cloudtasks.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  vision.googleapis.com

echo "=== 서비스계정 생성 ==="
# Runtime SA
if gcloud iam service-accounts describe "$RUNTIME_SA" &>/dev/null; then
  echo "✓ $RUNTIME_SA 이미 존재"
else
  echo "생성 중: $RUNTIME_SA"
  gcloud iam service-accounts create "${RUNTIME_SA%@*}" \
    --display-name="Cloud Run runtime"
fi

# Invoker SA
if gcloud iam service-accounts describe "$INVOKER_SA" &>/dev/null; then
  echo "✓ $INVOKER_SA 이미 존재"
else
  echo "생성 중: $INVOKER_SA"
  gcloud iam service-accounts create "${INVOKER_SA%@*}" \
    --display-name="Scheduler/Tasks invoker"
fi

echo "=== IAM 역할 부여 ==="
# cloudtasks.enqueuer 역할
gcloud projects add-iam-policy-binding "$GCP_PROJECT" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/cloudtasks.enqueuer" \
  --condition=None \
  --quiet 2>/dev/null || true

# invoker SA 에 act-as 권한
gcloud iam service-accounts add-iam-policy-binding "$INVOKER_SA" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/iam.serviceAccountUser" \
  --condition=None \
  --quiet 2>/dev/null || true

# (v4) 접수 서비스(INVOKER_SA 로 실행)도 Cloud Tasks 에 적재(즉시 확인 · 비동기 적용 작업)하고, 두 서비스 모두
#      예약된 확인을 조회 · 취소(예고 삭제 시 · 관리 페이지 「예정된 확인」)한다. 적재한 태스크의 OIDC 토큰을
#      INVOKER_SA 명의로 만들려면 접수 서비스가 자기 자신에 대한 serviceAccountUser 도 필요하다.
gcloud projects add-iam-policy-binding "$GCP_PROJECT" \
  --member="serviceAccount:$INVOKER_SA" \
  --role="roles/cloudtasks.enqueuer" \
  --condition=None \
  --quiet 2>/dev/null || true
gcloud iam service-accounts add-iam-policy-binding "$INVOKER_SA" \
  --member="serviceAccount:$INVOKER_SA" \
  --role="roles/iam.serviceAccountUser" \
  --condition=None \
  --quiet 2>/dev/null || true
for SA in "$RUNTIME_SA" "$INVOKER_SA"; do
  for ROLE in roles/cloudtasks.viewer roles/cloudtasks.taskDeleter; do
    gcloud projects add-iam-policy-binding "$GCP_PROJECT" \
      --member="serviceAccount:$SA" \
      --role="$ROLE" \
      --condition=None \
      --quiet 2>/dev/null || true
  done
done

# (v4.5.10) 이미지 판독 예비(Cloud Vision) — 관리 페이지(mewtype-telegram, INVOKER_SA)가 운영자 허가 때만 부른다.
# 호출에 할당량 프로젝트 헤더를 붙이므로 serviceusage.services.use 가 필요하다. 월 900건 상한은 앱이 센다(ops ocr_pending.json).
gcloud projects add-iam-policy-binding "$GCP_PROJECT" \
  --member="serviceAccount:$INVOKER_SA" \
  --role="roles/serviceusage.serviceUsageConsumer" \
  --condition=None \
  --quiet 2>/dev/null || true

# secretmanager.secretAccessor 역할 (RUNTIME_SA = 메인, INVOKER_SA = mewtype-telegram 실행 계정)
for SA in "$RUNTIME_SA" "$INVOKER_SA"; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT" \
    --member="serviceAccount:$SA" \
    --role="roles/secretmanager.secretAccessor" \
    --condition=None \
    --quiet 2>/dev/null || true
done

# Cloud Scheduler / Cloud Tasks 서비스 에이전트가 INVOKER_SA 로 OIDC 토큰을 발급하려면
# 각 에이전트에 INVOKER_SA 에 대한 tokenCreator 권한이 필요하다 (신규 프로젝트는 자동 부여되기도 하나 명시).
PROJECT_NUMBER="$(gcloud projects describe "$GCP_PROJECT" --format='value(projectNumber)')"
for AGENT in \
  "service-${PROJECT_NUMBER}@gcp-sa-cloudscheduler.iam.gserviceaccount.com" \
  "service-${PROJECT_NUMBER}@gcp-sa-cloudtasks.iam.gserviceaccount.com" \
; do
  gcloud iam service-accounts add-iam-policy-binding "$INVOKER_SA" \
    --member="serviceAccount:${AGENT}" \
    --role="roles/iam.serviceAccountTokenCreator" \
    --condition=None \
    --quiet 2>/dev/null || true
done

echo "=== Cloud Tasks 큐 생성/설정 ==="
# max-concurrent-dispatches=1: wake 를 순차 발화(data 브랜치 쓰기 직렬화). 생성/기존 모두 강제.
if gcloud tasks queues describe "$TASKS_QUEUE" --location="$GCP_LOCATION" &>/dev/null; then
  echo "✓ $TASKS_QUEUE 큐 이미 존재 — 설정 갱신"
  gcloud tasks queues update "$TASKS_QUEUE" --location="$GCP_LOCATION" \
    --max-concurrent-dispatches=1
else
  echo "생성 중: $TASKS_QUEUE"
  gcloud tasks queues create "$TASKS_QUEUE" --location="$GCP_LOCATION" \
    --max-concurrent-dispatches=1
fi

# (v4.5.2) PubSub 전용 큐 — 알림이 몰려도 확인 · 신곡 등록을 5초에 1건으로 흘려, 쓰기 서비스(동시 1건)가 쉬지 않고 바빠지지 않게 한다
#          (그 틈으로 트윗 저장 등 접수 서비스의 동기 쓰기가 들어간다). 쓰기 서비스가 바빠 거절(429)하면 5초부터 다시 시도.
WEBSUB_QUEUE="${WEBSUB_QUEUE:-mewtype-websub}"
_WSQ_OPTS=(--max-concurrent-dispatches=1 --max-dispatches-per-second=0.2 --max-attempts=20 --min-backoff=5s --max-backoff=300s)
if gcloud tasks queues describe "$WEBSUB_QUEUE" --location="$GCP_LOCATION" &>/dev/null; then
  echo "✓ $WEBSUB_QUEUE 큐 이미 존재 — 설정 갱신"
  gcloud tasks queues update "$WEBSUB_QUEUE" --location="$GCP_LOCATION" "${_WSQ_OPTS[@]}"
else
  echo "생성 중: $WEBSUB_QUEUE"
  gcloud tasks queues create "$WEBSUB_QUEUE" --location="$GCP_LOCATION" "${_WSQ_OPTS[@]}"
fi

echo "=== Secret Manager 시크릿 생성 ==="

# 시크릿 생성 헬퍼: env 에 값이 있으면 그대로 쓰고, 없으면 프롬프트.
create_secret () {
  local name="$1" prompt="$2" value="${3:-}"
  if gcloud secrets describe "$name" &>/dev/null; then
    echo "✓ $name 이미 존재 (갱신하려면 gcloud secrets versions add)"
    return
  fi
  if [[ -z "$value" ]]; then
    echo "$prompt (에코 안 됨):"
    read -rs value
    echo
  else
    echo "생성 중: $name (env 값 사용)"
  fi
  printf '%s' "$value" | gcloud secrets create "$name" \
    --data-file=- --replication-policy=automatic
}

create_secret YOUTUBE_API_KEY "YouTube API 키를 입력하세요" "${YOUTUBE_API_KEY:-}"
create_secret GITHUB_TOKEN "GitHub fine-grained PAT를 입력하세요 (Contents R/W)" "${GITHUB_TOKEN:-}"
create_secret TELEGRAM_BOT_TOKEN "BotFather 봇 토큰" "${TELEGRAM_BOT_TOKEN:-}"
create_secret TELEGRAM_WEBHOOK_SECRET "webhook secret (임의 문자열)" "${TELEGRAM_WEBHOOK_SECRET:-}"
# v2.3 X 릴레이 — 폰(Automate)이 mewtype-telegram /ingest 에 붙이는 공유 시크릿.
create_secret INGEST_SECRET "ingest secret (임의 문자열, 폰 Automate 에도 동일하게)" "${INGEST_SECRET:-}"
# v3 외부 LLM(Groq) — notice 제목 추출 + notice/개인트윗 번역. 없으면 번역 비활성(원문 노출).
create_secret GROQ_API_KEY "Groq API 키 (v3 번역/제목추출, 없으면 빈 값 Enter)" "${GROQ_API_KEY:-}"
# v3.5 healthchecks.io — /monitor 백엔드 상태 조회용 read-only API 키. 없으면 기능 비활성.
create_secret HEALTHCHECKS_IO_READONLEY_TOKEN "healthchecks.io read-only API 키 (/monitor 백엔드 상태 조회용, 없으면 빈 값 Enter)" "${HEALTHCHECKS_IO_READONLEY_TOKEN:-}"
# v3.8.9 Vercel REST API 토큰 — /monitor 의 배포 시도 수(Hobby 하루 100회 한도) 조회용. 없으면 "확인 불가".
create_secret VERCEL_TOKEN "Vercel API 토큰 (/monitor 배포 시도 수 조회용, 없으면 빈 값 Enter)" "${VERCEL_TOKEN:-}"

# (v4) 관리 페이지 로그인 링크 서명 키 — 값이 없으면 임의 생성(운영자가 알 필요 없음)
create_secret "${ADMIN_SECRET_NAME:-ADMIN_SECRET}" "관리 페이지 서명 키" "${ADMIN_SECRET:-$(python -c 'import secrets;print(secrets.token_hex(32))')}"

# (v4.5.0) PubSub(WebSub) 허브 서명 키 — 구독 때 허브에 넘기는 hub.secret. 접수 서비스가 알림의 X-Hub-Signature 를 검증하고
# 쓰기 서비스가 구독 갱신에 쓴다. 값이 없으면 임의 생성(운영자가 알 필요 없음).
create_secret WEBSUB_SECRET "PubSub 서명 키" "${WEBSUB_SECRET:-$(python -c 'import secrets;print(secrets.token_hex(24))')}"

echo "=== 셋업 완료 ==="

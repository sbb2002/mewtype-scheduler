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
  cloudbuild.googleapis.com

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

echo "=== Cloud Tasks 큐 생성 ==="
if gcloud tasks queues describe "$TASKS_QUEUE" --location="$GCP_LOCATION" &>/dev/null; then
  echo "✓ $TASKS_QUEUE 큐 이미 존재"
else
  echo "생성 중: $TASKS_QUEUE"
  gcloud tasks queues create "$TASKS_QUEUE" --location="$GCP_LOCATION"
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

echo "=== 셋업 완료 ==="

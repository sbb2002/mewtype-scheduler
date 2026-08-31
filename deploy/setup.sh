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

# secretmanager.secretAccessor 역할
gcloud projects add-iam-policy-binding "$GCP_PROJECT" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/secretmanager.secretAccessor" \
  --condition=None \
  --quiet 2>/dev/null || true

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
# YOUTUBE_API_KEY
if gcloud secrets describe YOUTUBE_API_KEY &>/dev/null; then
  echo "✓ YOUTUBE_API_KEY 이미 존재"
else
  echo "생성 중: YOUTUBE_API_KEY"
  echo "YouTube API 키를 입력하세요 (에코 안 됨):"
  read -rs YOUTUBE_API_KEY
  echo "$YOUTUBE_API_KEY" | gcloud secrets create YOUTUBE_API_KEY \
    --data-file=- \
    --replication-policy=automatic
fi

# GITHUB_TOKEN
if gcloud secrets describe GITHUB_TOKEN &>/dev/null; then
  echo "✓ GITHUB_TOKEN 이미 존재"
else
  echo "생성 중: GITHUB_TOKEN"
  echo "GitHub fine-grained PAT를 입력하세요 (에코 안 됨, Contents R/W 권한):"
  read -rs GITHUB_TOKEN
  echo "$GITHUB_TOKEN" | gcloud secrets create GITHUB_TOKEN \
    --data-file=- \
    --replication-policy=automatic
fi

echo "=== 셋업 완료 ==="

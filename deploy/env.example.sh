#!/usr/bin/env bash
# 복사해서 deploy/env.sh 로 저장하고 값 채우기 (deploy/env.sh 는 .gitignore)
export GCP_PROJECT="your-project-id"
export GCP_LOCATION="asia-northeast1"          # Cloud Run / Tasks / Scheduler 동일 리전
export SERVICE_NAME="mewtype-backend"
export TASKS_QUEUE="mewtype-wake"
export RUNTIME_SA="mewtype-backend@${GCP_PROJECT}.iam.gserviceaccount.com"
export INVOKER_SA="mewtype-invoker@${GCP_PROJECT}.iam.gserviceaccount.com"
export GITHUB_REPO="sbb2002/mewtype-scheduler"
export DATA_BRANCH="data"
# Secret Manager 에 넣을 값 (스크립트가 생성 시 물어봄 / 또는 미리 gcloud secrets create)
#   YOUTUBE_API_KEY, GITHUB_TOKEN(fine-grained PAT: Contents R/W, 해당 레포)
#   TELEGRAM_BOT_TOKEN (BotFather 봇 토큰)
#   TELEGRAM_WEBHOOK_SECRET (webhook secret)
export TELEGRAM_BOT_TOKEN=""
export TELEGRAM_CHAT_ID=""                      # 비밀 아님 (env 로 주입, secret 아님)
export TELEGRAM_WEBHOOK_SECRET=""
export HEALTHCHECK_URL=""                       # 비밀 아님 (env 로 주입, secret 아님). healthchecks.io ping URL
# SERVICE_URL 은 deploy.sh 가 배포 후 채워서 재설정

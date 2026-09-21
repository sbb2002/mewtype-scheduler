#!/usr/bin/env bash
# 복사해서 deploy/env.sh 로 저장하고 값 채우기 (deploy/env.sh 는 .gitignore)
export GCP_PROJECT="your-project-id"
export GCP_LOCATION="asia-northeast1"          # Cloud Run / Tasks / Scheduler 동일 리전
export SERVICE_NAME="mewtype-backend"
export TASKS_QUEUE="mewtype-wake"
export RUNTIME_SA="mewtype-backend@${GCP_PROJECT}.iam.gserviceaccount.com"
export INVOKER_SA="mewtype-invoker@${GCP_PROJECT}.iam.gserviceaccount.com"
export GITHUB_REPO="sbb2002/mewtype-scheduler-data"
export DATA_BRANCH="data"
# Secret Manager 에 넣을 값 (스크립트가 생성 시 물어봄 / 또는 미리 gcloud secrets create)
#   YOUTUBE_API_KEY, GITHUB_TOKEN(fine-grained PAT: Contents R/W, 해당 레포)
#   TELEGRAM_BOT_TOKEN (BotFather 봇 토큰)
#   TELEGRAM_WEBHOOK_SECRET (webhook secret)
#   INGEST_SECRET (X 릴레이 시크릿, 폰 Automate 와 동일)
#   GROQ_API_KEY (Groq 외부 LLM, 번역/제목추출용 — 없으면 원문 노출)
#   HEALTHCHECKS_IO_READONLEY_TOKEN (healthchecks.io read-only API 키, /monitor 백엔드 상태 조회 — 없으면 기능 비활성)
export TELEGRAM_BOT_TOKEN=""
export TELEGRAM_CHAT_ID=""                      # 비밀 아님 (env 로 주입, secret 아님)
export TELEGRAM_WEBHOOK_SECRET=""
export HEALTHCHECK_URL=""                       # 비밀 아님 (env 로 주입, secret 아님). healthchecks.io ping URL
# 명령 옵션들 (모두 필수 아님 — 기본값 0)
export INGEST_DRY_RUN="0"                       # 1: /ingest 가 preview.json 을 안 쓰고 DM 만 회신
export INGEST_ECHO="0"                          # 1: /ingest 가 파싱 안 하고 받은 텍스트만 DM 회신
export INGEST_YT_ENABLED="0"                    # 1: /ingest 가 YouTube 앱 푸시알림도 처리
# SERVICE_URL 은 deploy.sh 가 배포 후 채워서 재설정
# (v3.8.2) DB 관제소(mewtype-db-tower) 는 deploy_tower.sh 로 먼저 배포. 백엔드·제어 채널 배포 스크립트가 그 URL 을 TOWER_URL 로 자동 주입

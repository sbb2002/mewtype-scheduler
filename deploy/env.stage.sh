# (v4) 스테이징 덮어쓰기 — `STAGE=1 bash deploy/deploy.sh` 처럼 쓰면 env.sh 다음에 이 파일을 읽는다.
# 운영과 같은 이미지 · 같은 Secret 을 쓰되, 서비스 · 큐 · 데이터 브랜치를 전부 따로 둔다(운영 무영향).
# 비밀 값 없음 — git 에 올린다.
export SERVICE_NAME="mewtype-backend-stage"
export TELEGRAM_SERVICE="mewtype-telegram-stage"
export TASKS_QUEUE="mewtype-wake-stage"
export DATA_BRANCH="data-stage"
export MONITOR_BRANCH="monitoring-stage"
export OPS_BRANCH="ops-stage"
export TELEGRAM_CHAT_ID=""                # 스테이징은 운영자에게 DM 을 보내지 않는다
export HEALTHCHECK_URL=""                 # 운영 생존 신호(healthchecks.io)를 건드리지 않는다
export ADMIN_SECRET_NAME="ADMIN_SECRET_STAGE"

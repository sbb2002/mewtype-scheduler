#!/usr/bin/env bash
set -euo pipefail

source deploy/env.sh

# (v3.8.2) DB 관제소 — data 저장소 접근의 유일한 문. 백엔드(mewtype-backend)·제어 채널(mewtype-telegram)
# 보다 **먼저** 배포한다(두 서비스가 TOWER_URL 로 이 서비스를 가리키므로).
#
# --concurrency=64 --max-instances=1 --min-instances=0:
#   · 백엔드(--concurrency=1)와 다르다. 관제소는 요청이 프로세스 안에서 FIFO 로 줄을 서야 대기 상한(503)을
#     통제할 수 있으므로 여러 요청이 동시에 들어와 있어야 한다(순서·직렬화는 tower.Tower 가 보장).
#   · max-instances=1: FIFO 가 서비스 전체에서 성립하려면 인스턴스가 하나여야 한다.
#   · min-instances=0: 상시 ON 아님(scale-to-zero). 꺼지면 큐·쿨다운·ETag 캐시가 사라지지만 정확성엔 영향 없음.
# --threads=64: 줄서기 중인 요청도 스레드를 하나씩 쥔다 → concurrency 와 같거나 크게.
# CALLER_SAS: 백엔드(RUNTIME_SA)·제어 채널(INVOKER_SA) 두 서비스계정을 모두 허용 (oidc.verify_request 가 쉼표 목록 지원).
#   값에 쉼표가 있어 gcloud 대체 구분자(^@^)를 쓴다.
echo "=== mewtype-db-tower 배포 ==="
gcloud run deploy mewtype-db-tower \
  --source . \
  --region "$GCP_LOCATION" \
  --no-allow-unauthenticated \
  --service-account "$RUNTIME_SA" \
  --concurrency=64 \
  --max-instances=1 \
  --min-instances=0 \
  --timeout=90 \
  --command=gunicorn \
  --args="--bind=0.0.0.0:8080,--workers=1,--threads=64,--timeout=90,src.backend.tower_app:app" \
  --set-secrets "GITHUB_TOKEN=GITHUB_TOKEN:latest" \
  --set-env-vars "^@^GITHUB_REPO=$GITHUB_REPO@DATA_BRANCH=$DATA_BRANCH@CALLER_SAS=$INVOKER_SA,$RUNTIME_SA@SERVICE_URL=https://placeholder.invalid"
# SERVICE_URL(= OIDC audience) 은 배포 후 실제 URL 을 알 수 있으므로 일단 placeholder 로 부팅시키고 아래에서 교체한다.

echo "=== 서비스 URL 조회 ==="
URL=$(gcloud run services describe mewtype-db-tower \
  --region "$GCP_LOCATION" \
  --format='value(status.url)')

echo "=== SERVICE_URL 환경변수 재설정 ==="
gcloud run services update mewtype-db-tower \
  --region "$GCP_LOCATION" \
  --update-env-vars "SERVICE_URL=$URL"

echo "=== Invoker 권한 부여 (백엔드 · 제어 채널) ==="
for SA in "$RUNTIME_SA" "$INVOKER_SA"; do
  gcloud run services add-iam-policy-binding mewtype-db-tower \
    --region "$GCP_LOCATION" \
    --member "serviceAccount:$SA" \
    --role roles/run.invoker \
    --quiet 2>/dev/null || true
done

echo "=== 배포 완료 ==="
echo "TOWER_URL=$URL"
echo "다음: deploy/deploy.sh (백엔드) → deploy/deploy_telegram.sh (제어 채널) 순서로 배포 — 둘 다 TOWER_URL 을 자동으로 읽는다."

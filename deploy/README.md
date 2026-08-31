# Cloud Run 배포 가이드

## 배포 순서

### 1. 셋업 (초회 1회)

```bash
# env.sh 생성
cp deploy/env.example.sh deploy/env.sh
# env.sh 의 GCP_PROJECT, GCP_LOCATION 등을 실제 값으로 수정
vi deploy/env.sh

# 셋업 실행 (API 활성화, SA, IAM, 큐, 시크릿 생성)
bash deploy/setup.sh
# 프롬프트에서 YOUTUBE_API_KEY, GITHUB_TOKEN 입력
```

### 2. 배포

```bash
bash deploy/deploy.sh
# Cloud Run 배포 후 SERVICE_URL 자동 설정
```

### 3. 스케줄러 설정

```bash
bash deploy/scheduler.sh
# baseline (JST 06:00) + light (UTC 3h 간격) 생성/업데이트
```

## 재배포

```bash
bash deploy/deploy.sh
bash deploy/scheduler.sh
```

## 롤백

이전 리비전으로 되돌리기:

```bash
gcloud run services update-traffic "$SERVICE_NAME" \
  --region "$GCP_LOCATION" \
  --to-revisions PREVIOUS=100
```

## 로그 확인

```bash
gcloud run services logs read "$SERVICE_NAME" \
  --region "$GCP_LOCATION" \
  --limit 50
```

## 문제 해결

- 배포 실패: `gcloud run deploy` 출력 확인, Secret Manager 값 검증
- 스케줄러 미동작: `gcloud scheduler jobs describe mewtype-baseline --location="$GCP_LOCATION" --format=json` 로 상태 확인
- 권한 오류: `deploy/setup.sh` 의 IAM 섹션 다시 실행

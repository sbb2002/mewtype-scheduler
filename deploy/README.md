# Cloud Run 배포 가이드

## v2.1 Telegram 모니터링 & 제어

### 사전 작업 (운영자가 미리 준비)

1. **@BotFather** 로 봇 생성 → `TELEGRAM_BOT_TOKEN` 취득
   - `/setcommands` 로 `status,pause,resume` 등록(선택)
2. 봇과 DM 시작 → `https://api.telegram.org/bot<token>/getUpdates` 로 자기 `chat.id` 확인 → `TELEGRAM_CHAT_ID`
3. `TELEGRAM_WEBHOOK_SECRET` = 임의의 긴 랜덤 문자열 생성 (예: `openssl rand -hex 32`)
4. **healthchecks.io** 무료 가입
   - check 생성 (period 3h / grace 40m)
   - ping URL → `HEALTHCHECK_URL`
   - Integrations → Telegram 연결
5. `.env` 에 추가:
   ```
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_CHAT_ID=...
   TELEGRAM_WEBHOOK_SECRET=...
   HEALTHCHECK_URL=https://hc-ping.com/....
   INGEST_SECRET=...        # v2.3 X 릴레이 — 임의 랜덤 문자열 (openssl rand -hex 24)
   ```

### v2.3 — X 예고 릴레이 (`mewtype-telegram` `POST /ingest`)

폰(Automate)이 삼성 브라우저 X 웹푸시 알림 텍스트를 이 엔드포인트로 직접 POST →
`@BDP_yumemita` 일일 스케줄 트윗을 파싱해 `schedule.json` 의 `scheduled` 행으로 반영.
설계: `docs/plan/v2_3_x_relay.md`.

- `INGEST_SECRET` 을 Secret Manager 에 등록(`setup.sh` 가 처리) → `deploy_telegram.sh` 가 주입.
- **폰 Automate** — HTTP request(POST):
  - URL `https://<mewtype-telegram-url>/ingest`
  - Header `X-Ingest-Secret: <INGEST_SECRET>`
  - Content-Type `application/x-www-form-urlencoded`
  - Body `text=` + urlEncode(알림 전체 본문)  (선택: `&src=<계정핸들>`)
- 형식이 아니거나 `control.json.paused` 면 no-op. 결과·경고는 운영자 DM 으로 회신.

### 배포 순서 (v2.1)

```bash
bash deploy/setup.sh          # 시크릿 등록 (TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, INGEST_SECRET)
bash deploy/deploy.sh         # 메인 서비스 재배포 (Telegram 알림 기능 활성)
bash deploy/deploy_telegram.sh   # 공개 webhook 서비스 신규 배포
bash deploy/telegram_webhook.sh  # setWebhook 등록
```

배포 후:
```bash
# 봇에 /status 전송해서 응답 확인
# 로그 확인: gcloud run services logs read mewtype-telegram --region asia-northeast1
```

주의:
- `mewtype-telegram` 은 **INVOKER_SA 로 실행**된다 (`deploy_telegram.sh`). `/resume` 이 메인 `/tick` 을
  OIDC 로 호출할 때 메인이 caller email == INVOKER_SA 를 요구하기 때문. RUNTIME_SA 로 실행 시
  `token email mismatch` 403 → "동기화 상태 확인 불가" 로 나타남.
- `setup.sh` 가 INVOKER_SA 에 `secretmanager.secretAccessor` 를 부여한다 (webhook 서비스의 GITHUB_TOKEN
  등 시크릿 접근용). 누락 시 `mewtype-telegram` 배포는 되나 런타임에 시크릿을 못 읽음.

### 롤백 (v2.1)

```bash
# webhook 해제
bash deploy/telegram_webhook.sh delete

# mewtype-telegram 서비스 삭제
gcloud run services delete mewtype-telegram --region asia-northeast1

# 메인 서비스: TELEGRAM_BOT_TOKEN env 제거 후 재배포 (알림 비활성, v2.0 동작 유지)
# 또는 단순히 deploy.sh 재실행 (env 변수 제거된 상태의 .env 사용)
```

---

## 배포 순서 (v2.0)

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

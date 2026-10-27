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
- **먼저 DRY-RUN 으로 검증**: `INGEST_DRY_RUN=1` (env.sh 또는
  `gcloud run services update mewtype-telegram --region asia-northeast1 --update-env-vars INGEST_DRY_RUN=1`)
  → `/ingest` 가 저장 없이 받은 원문·파싱결과만 DM 회신. 푸시 알림이 잘리지 않고
  엔트리 전부 오는지 확인되면 `INGEST_DRY_RUN=0` 으로 되돌리고 재배포.

### v4.9.0 — 상시 조사 · 일일 묶음 잡 (2026-10-27 배포)

배포 순서(명세 `ref/self-reply/patch_spec.md` §8):
1. `bash deploy/setup.sh` — 큐 2개 추가: `mewtype-gapfill`(동시 1 · 3회), `mewtype-daily`(동시 1 · 4회 · 30~300초). 기존 큐 옵션은 그대로.
2. `bash deploy/deploy.sh` — 쓰기 서비스 `/daily` · 새 데이터 모양(`reply_to_id`) · 글타래 수명. env `DAILY_QUEUE`(기본 `mewtype-daily`).
3. `bash deploy/deploy_telegram.sh` && `bash deploy/telegram_webhook.sh` — 접수 서비스 `/gap-check` · `/gap-fill`. env `GAPFILL_QUEUE`(기본 `mewtype-gapfill`) · `ADMIN_BASE_URL`(자기 주소 — 보충 작업 대상 · OIDC audience).
   `mewtype-telegram` 이 `INVOKER_SA` 로 떠 있어야 Scheduler · Cloud Tasks 의 OIDC 토큰이 맞는다(기존과 같음).
4. 스테이징 수동 시험(`STAGE=1 bash deploy/deploy.sh` 등 — 스테이징은 Scheduler 를 만들지 않는다, `STAGE=1 bash deploy/scheduler.sh` 는 아무것도 안 하고 끝남).
5. `bash deploy/scheduler.sh` — **KST 05:50~06:30 을 피해서** 실행(스크립트가 그 창에선 거부). 새 잡 `mewtype-daily`(매일 06:00 KST) · `mewtype-gapcheck`(매분)을 만든 **뒤** 옛 잡 `mewtype-baseline` · `mewtype-monitor` · `mewtype-websub-renew` 을 지운다. 결과: 잡 3개(`mewtype-light` · `mewtype-daily` · `mewtype-gapcheck`).
   접수 서비스 주소는 `TELEGRAM_SERVICE`(기본 `mewtype-telegram`)로 조회한다.

되돌리기: 옛 `scheduler.sh`(main 판)로 옛 잡 3개를 다시 만든 뒤 `mewtype-daily` · `mewtype-gapcheck` 를 지운다(이 순서 — monitor 가 하루 빠지지 않게). Cloud Run 은 직전 리비전으로 트래픽을 되돌린다(VERSION.md 에 적힌 리비전). 옛 코드는 `reply_to_id` 를 모르는 키로 무시하고, 늘어난 `expires_at` 은 그대로 읽는다.

### v4.5.2 — PubSub 버스트 대비 (PubSub 전용 큐 `mewtype-websub`)

순서: ① 큐 생성(`setup.sh` 의 해당 부분과 같은 명령 — `setup.sh` 전체는 기존 큐 설정까지 다시 쓰므로 필요한 것만):
`gcloud tasks queues create mewtype-websub --location=asia-northeast1 --max-concurrent-dispatches=1 --max-dispatches-per-second=0.2 --max-attempts=20 --min-backoff=5s --max-backoff=300s`
② `deploy.sh`(쓰기 서비스 — 새 `/wake` 본문 · 재확인을 먼저 이해해야 한다) ③ `deploy_telegram.sh`(접수 서비스 — 큐가 없으면 알림 예약이 실패해 503).
롤백 = 두 서비스를 이전 리비전 `mewtype-backend-00152-x42` · `mewtype-telegram-00109-m2b` 로(명령은 아래 「롤백」 절, 큐는 남겨 둬도 무해). 스테이징: `env.stage.sh` 의 `WEBSUB_QUEUE=mewtype-websub-stage`.

### v4.5.0 — PubSub(WebSub) 수신 (`mewtype-telegram` `/websub/<이름>` + `mewtype-backend` `/websub-renew`)

허브(`pubsubhubbub.appspot.com`)가 멤버 5채널 · 뮤타입 음원 채널의 변경을 접수 서비스로 POST → 방송 발견 · 신곡 등록을 RSS 폴링 대신 푸시로. 설계 `docs/SPEC.md` §8.16.

배포 순서(운영자 결정 · 한 번에 하나씩):
1. `bash deploy/setup.sh` — Secret `WEBSUB_SECRET`(허브 서명 키) 생성. 값이 없으면 임의 생성(운영자가 알 필요 없음).
2. `bash deploy/deploy_telegram.sh` — 콜백 `GET/POST /websub/<이름>` + 서명 검증. **먼저** 해야 다음 단계가 콜백 주소를 안다.
3. `bash deploy/deploy.sh` — 쓰기 서비스에 `WEBSUB_SECRET` · `WEBSUB_CALLBACK_BASE`(접수 서비스 URL, 배포 때 자동 조회) · `WEBSUB_REPLACE_RSS`(기본 0) 주입.
4. `bash deploy/scheduler.sh` — `mewtype-websub-renew`(매일 KST 06:20 → `POST /websub-renew`).
5. 갱신 잡을 한 번 수동 실행(`gcloud scheduler jobs run mewtype-websub-renew --location asia-northeast1`) → 이벤트 로그(`monitoring` 브랜치 `monitoring/events-*.jsonl`)에
   `"flow": "websub"` · `"action": "verify"` 가 6개(멤버 5 + 음원 1) 뜨면 구독 성공.
6. **이중 운영 관찰**(`WEBSUB_REPLACE_RSS=0` — 알림도 받고 폴링도 그대로): `action=notify` 가 새 영상마다 찍히고, 첫 실알림에서 `action=reject`(서명 헤더 없음)가 **안** 뜨는지 확인.
7. 문제 없으면 `env.sh` 에 `export WEBSUB_REPLACE_RSS=1` 후 `deploy.sh` — light 틱이 RSS · 신곡 감지를 생략(일일 baseline 만 안전망). `--set-env-vars` 는 매번 전체를 다시 쓰므로 env.sh 에 둬야 다음 배포에도 유지된다.

롤백: `WEBSUB_REPLACE_RSS=0` 으로 재배포하면 폴링이 즉시 복귀. 완전 철회는 `mewtype-websub-renew` 잡을 삭제(구독은 5일 안에 자연 만료, 그동안 콜백은 알림을 받아도 폴링과 중복될 뿐 무해).

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

이전 리비전으로 트래픽을 돌린다(이미지 재빌드 없음, 몇 초 안에 반영). **리비전 이름을 직접 써야 한다** — gcloud 에 「직전 리비전」 키워드는 없다
(2026-10-19 까지 여기 적혀 있던 `--to-revisions PREVIOUS=100` 은 동작하지 않는 명령이었다).

```bash
# 1) 되돌릴 리비전 이름 찾기 — 최근 것부터. 버전별 배포 리비전은 docs/VERSION.md 의 「배포 …」 표기에도 있다
gcloud run revisions list --service mewtype-backend  --region asia-northeast1 --limit 5
gcloud run revisions list --service mewtype-telegram --region asia-northeast1 --limit 5

# 2) 그 리비전으로 트래픽 100% (서비스마다. 예: v4.5.2 → v4.5.1 상태)
gcloud run services update-traffic mewtype-backend  --region asia-northeast1 --to-revisions mewtype-backend-00152-x42=100
gcloud run services update-traffic mewtype-telegram --region asia-northeast1 --to-revisions mewtype-telegram-00109-m2b=100

# 3) 확인 — 트래픽이 그 리비전 100% 인지
gcloud run services describe mewtype-backend --region asia-northeast1 --format='value(status.traffic)'
```

- **`mewtype-backend` 는 배포마다 리비전이 2개 생긴다** — `deploy.sh` 가 먼저 `SERVICE_URL=https://placeholder.invalid` 로 올린 뒤 실제 URL 로 한 번 더 갱신하기 때문.
  앞의 것(예: `00153-8dm`)은 인증 대상 주소가 틀려 모든 `/tick` · `/wake` · `/write` 를 403 으로 거절하므로 **절대 그쪽으로 되돌리지 않는다**.
  `docs/VERSION.md` 에 적힌 리비전(뒤의 것)을 쓰거나 `gcloud run revisions describe <리비전> --region asia-northeast1 --format=json` 의 `SERVICE_URL` 로 확인.
- 두 서비스 공통 코드(`writers.py` · `telegram_app.py` · `websub.py` 등)가 바뀐 버전이면 **두 서비스를 함께** 되돌린다.
- 롤백하면 트래픽이 그 리비전에 고정된다. 고쳐서 다시 배포한 뒤에는 새 리비전이 트래픽을 받는지 3) 으로 확인하고,
  고정이 남아 있으면 `gcloud run services update-traffic <서비스> --region asia-northeast1 --to-latest` 로 최신 리비전에 돌린다.
- 리비전만 되돌리고 `main` 코드는 그대로이므로 다음 `deploy.sh` 는 다시 새 코드를 올린다 — 코드까지 되돌릴 거면 병합 커밋을 revert 한 뒤 배포.
- 버전별 특수 사항은 위의 버전 절을 본다(예: v4.5.0 은 `WEBSUB_REPLACE_RSS=0` 재배포만으로 폴링 복귀).

## 로그 확인

```bash
gcloud run services logs read "$SERVICE_NAME" \
  --region "$GCP_LOCATION" \
  --limit 50
```

## 문제 해결

- 배포 실패: `gcloud run deploy` 출력 확인, Secret Manager 값 검증
- 스케줄러 미동작: `gcloud scheduler jobs describe mewtype-daily --location="$GCP_LOCATION" --format=json` 로 상태 확인
- 권한 오류: `deploy/setup.sh` 의 IAM 섹션 다시 실행

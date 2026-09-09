# v3 골라이브 런북 (실행 기록 — 2026-09-09)

v2 → v3 라이브 전환. **콜드 스타트**(데이터 마이그레이션 없음, `v3_draft.md` 확정).
아래는 실제 실행한 순서. 재실행/롤백 시 참조.

## 전제

- v3 브랜치 코드 완성 (`v3_impl_spec.md` WP-0~19 완료, 15모듈 self-test + 프론트 selfcheck 통과).
- Vercel 프로덕션 브랜치 = `main` (Root Directory `src/frontend`).
- Cloud Run 서비스 `mewtype-backend` / `mewtype-telegram` (리전 `asia-northeast1`).
  Cloud Run URL 은 리비전이 바뀌어도 **불변** → 스케줄러/webhook 재설정 대개 불필요.

## 실행 순서

| # | 명령 / 동작 | 결과 |
|---|---|---|
| A | `gcloud secrets create GROQ_API_KEY --data-file=-` (`.env` 값) + 런타임 SA 에 `secretAccessor` | Secret Manager 에 `GROQ_API_KEY` |
| B | `data` 브랜치 `control.json` → `paused:true` 커밋·푸시 | v2 tick/wake no-op (전환 창) |
| C | `git checkout main && git merge v3` (FF 불가 → merge 커밋. `SPEC.md` 충돌만 `--theirs`) → self-test → `git push origin main` | Vercel 이 v3 프론트 빌드 시작 |
| D | `data` 브랜치 수술: v2 파일 9종(`schedule/archive/pending/ingest_queue/admin_state/notice_archive/tweet_archive/notices/tweets.json`) → `.old/`. 루트에 v3 빈 파일 시드: `preview.json`(`{channel_order:[],channels:{},generated_at:null,items:[]}`)·`notices.json`(`{generated_at:null,notices:[]}`)·`tweets.json`(`{generated_at:null,tweets:{}}`). `control.json` 유지. 커밋·푸시 | `data` 브랜치 v3 레이아웃 |
| E | `bash deploy/deploy.sh` | `mewtype-backend` 새 리비전 100% + `SERVICE_URL` 재설정 + invoker 바인딩 |
| F | `bash deploy/deploy_telegram.sh` && `bash deploy/telegram_webhook.sh` | `mewtype-telegram` 새 리비전 + webhook 확인 |
| G | `data` 브랜치 `control.json` → `paused:false` 커밋·푸시 | v3 정상 가동 |
| H | `gcloud scheduler jobs run mewtype-baseline --location=asia-northeast1` | 즉시 tick — `preview.json` 최초 재구성 |
| I | 검증 (아래) | — |

### 검증 항목

- 백엔드 로그 `tick done: {... 'preview_changed': True, 'preview_items': N ...}` 에러 0.
- `raw.githubusercontent.com/.../data/preview.json` — v3 스키마(`pv_` id, `state`, `channels`).
- 프론트(`mewtype-schduler.vercel.app`) `js/config.js` 에 `PREVIEW_URL=.../preview.json`, 카드 렌더.
- 두 서비스 `severity>=WARNING` 로그 없음.

## 알려진 비블로커

- `deploy/scheduler.sh` — gcloud 신버전에서 `--headers=` 인자 오류(`--clear-headers` 로 대체됐음).
  스케줄러 잡은 URL 불변이라 이번엔 손댈 필요 없었음. **스크립트 수정 필요**(다음 리전 이전/URL 변경 시).
- `GET /healthz` 가 인프라 404 (`GET /` 는 `ok`, `/tick`·`/wake` 정상). 업타임 핑만 조용히 실패.
- LLM 프롬프트 미튜닝 — 실패 시 정규식/원문 폴백이라 무해. 실콘텐츠 유입 후 품질 보정.

## 롤백

```bash
# 1. Cloud Run 이전 리비전으로 트래픽
gcloud run services update-traffic mewtype-backend  --region=asia-northeast1 --to-revisions=<v2 revision>=100
gcloud run services update-traffic mewtype-telegram --region=asia-northeast1 --to-revisions=<v2 revision>=100
#    (골라이브 직전 v2 리비전: mewtype-backend-00023-9b7 / mewtype-telegram-00031-pxg)

# 2. data 브랜치 복원 — .old/ 파일을 루트로 되돌리고 v3 빈 파일 제거
git checkout data
git mv .old/schedule.json schedule.json   # ... 9종 전부
git rm preview.json && git rm -r .old      # (notices/tweets 는 .old/ 것으로 덮어쓰기)
git commit -m "rollback: v2 데이터 복원" && git push origin data

# 3. main — 머지 커밋 revert
git checkout main && git revert -m 1 <merge commit> && git push origin main   # Vercel 이 v2 프론트 재배포
```

- raw CDN 캐시(~5분) 때문에 프론트 복구는 몇 분 지연될 수 있음. 급하면 `control.json` `paused:true` 로 창을 닫음.

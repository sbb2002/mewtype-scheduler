# v4.9.0 배포 뒤 지켜볼 것 (2026-10-27 배포 — 다른 세션 · 다른 PC 인계용)

v4.9.0 = 자기 답글 보충 · 빠진 트윗 상시 조사 · 일일 묶음 잡 · 트윗 시트(마이너). 이 문서만 보고 관찰 · 판단할 수 있게 쓴다.
배경 = 같은 폴더 `patch_spec.md` · `ui_spec.md` · `verify_spec.md` · `verify_result_20261027.md`, 정본 = main `docs/VERSION.md` v4.9.0 · `docs/SPEC.md`.

## 배포 상태 (2026-10-27 KST 17:43~17:50)
- 병합 `2cad9f5`(PR #101), 태그 `v4.9.0`, 문서 커밋 `67993b0` · `bdb3f11`.
- Cloud Run: `mewtype-backend` **00188** · `mewtype-telegram` **00127** (롤백 = 00186 · 00126).
- Cloud Tasks 새 큐: `mewtype-gapfill`(동시 1 · 3회) · `mewtype-daily`(동시 1 · 4회 · 30~300초).
- Scheduler(3잡): `mewtype-light`(10분) · `mewtype-daily`(KST 06:00) · `mewtype-gapcheck`(매분). 옛 `mewtype-baseline` · `mewtype-monitor` · `mewtype-websub-renew` 삭제.
- Vercel: `main` 푸시로 v4.9.0 반영 확인(`js/config.js` APP_VERSION, `js/tweetlogic.js` 200).
- 스테이징: 같은 코드로 배포된 채 남겨 둠(`mewtype-backend-stage` · `mewtype-telegram-stage`, 큐 `mewtype-gapfill-stage` · `mewtype-daily-stage`, data-stage 에 10-27 운영 트윗 복사본). Scheduler 없음.

## 배포 직후 확인 (V5) — 결과
| # | 항목 | 결과 |
|---|---|---|
| V5-1 | Scheduler 정확히 3개 | 합격 |
| V5-2 | 상시 조사 매분 실행 · 403 0 | 합격(17:44 부터 매분 200, 1.5~2.7초) · 첫 몇 분 fxtwitter 404 경고 없음 |
| V5-3 | 폰 경로(배포 뒤 첫 멤버 트윗) | **미확인** — 아래 W3 |
| V5-4 | light tick | 합격(17:30 · 17:40 200) |
| V5-5 | 운영 화면 `?va=claude` | 합격 — 아라레 시트(실제 색 · 540px · 9글 · X 카드 로딩) 열기 · Esc 닫기, 콘솔 오류 0 |

## 지켜볼 것 (W)

### W1. 내일 아침 일일 묶음 잡 — 10-28 06:00~06:20 KST [가장 중요]
- 기대: 06:00 baseline tick 1회 → 06:10 `/monitor`(스냅샷 · 보관함 정리 · monitor DM **1번**) → 06:20 `/websub-renew` 1회.
- 확인:
  ```bash
  gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="mewtype-backend" AND (httpRequest.requestUrl:"/daily" OR httpRequest.requestUrl:"/monitor" OR httpRequest.requestUrl:"/websub-renew") AND timestamp>="2026-10-27T20:55:00Z" AND timestamp<="2026-10-27T21:40:00Z"' --format="value(timestamp,httpRequest.requestUrl,httpRequest.status)"
  ```
  운영자 텔레그램에 monitor DM 이 한 번만 왔는지(두 번이면 옛 잡이 남았거나 예약이 중복된 것).
- 실패하면: 옛 잡 3개 복구 — main v4.8.6 판 `deploy/scheduler.sh` 로 만들고(`git show v4.8.6:deploy/scheduler.sh > /tmp/s.sh`) `mewtype-daily` 삭제. KST 05:50~06:30 은 피할 것.

### W2. fxtwitter 최근 글 목록 404 — 시간대별 실패율 [결정 근거]
- 10-27 스테이징: 17:00 KST 정각 조회 5명 전부 404 → 17:02 미야코만 404 → 17:26 정상. 같은 시각 이 PC(가정 회선)는 200. 원인 미확정.
- 웹 사례(10-27 조사): 다른 프로젝트도 fxtwitter 프로필 · 목록 404 가 「오락가락(flaps)」 — 1.5초 간격 최대 2번 재시도로 대응(jev-desk PR #49). fxtwitter 관리자: 프로필 계열은 계정 프록시(빈 X 계정을 돌려 씀)가 필요(FxEmbed #1060) → 그 경로의 간헐 실패일 가능성. 자체 호스팅은 해결책 아님(계정 · X 의 IP 차단 문제를 떠안음, #1385).
- 우리 RSS 낮 시간대 실패(메모리 「RSS 시간대 편중」, KST 08~16시)와 같은 원인인지는 미확정 — 상대 서비스가 다름(YouTube vs X). 같은 종류(제공자 쪽 시간대 제한)일 수는 있음.
- 측정:
  ```bash
  # 운영 접수 서비스의 목록 실패 경고 — KST 시 단위로 세기(경고는 URL 이 달라야 다시 찍힌다: since 값이 매번 달라 대부분 찍힘)
  gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="mewtype-telegram" AND textPayload:"fxtwitter profile"' --freshness=1d --limit=2000 --format="value(timestamp,textPayload)"
  ```
  모니터 이벤트 `gap-check: fxtwitter 연속 실패 — 10분 쉼` / `재개` 쌍도 함께 센다(monitoring 브랜치 `events-YYYY-MM-DD.jsonl`).
- 판단 기준(제안): 시간대별 실패율이 높고 낮에 몰리면 → ① 1.5초 간격 2회 재시도 추가(20초 상한 안) ② 경고를 시간당 1회로 묶고 실패 수는 모니터 이벤트로(RSS 때와 같은 방식). 하루 종일 높으면 → 대안 조사(유료 제외 — 메모리 「유료 서비스 반려」).
- 스테이징 18:00 KST 정각 전체 조회 1회 예약해 둠(`gapcheck-hour18-…`) — 결과는 `verify_result_20261027.md` 끝에 추가.

### W3. 실제 보충이 들어오는지
- 폰이 빠뜨린 일반 글 → 모니터 `warn` 「gap-fill · <id> · +N분」 이 **10분 안**(N ≤ 10). 「폰 늦게 도착 · 보충 뒤 +N분」(ok)은 폰이 7분 넘게 늦은 것 — 따로 센다.
- 자기 답글 → `ok` 「gap-fill(자기 답글) · <id> · +N분」, 1~2분 안. 원글이 없으면 「원글 함께」 · 「원글 되살림」. **10-27 기준 48시간 안 자기 답글이 없어 실보충은 아직 한 번도 못 봄.**
- 같은 글이 폰 · 보충 양쪽으로 와도 예고 판정 · 변경 판정 · 새 트윗 DM 이 **한 번**인지(텔레그램 DM 중복 여부).
- 화면: 자기 답글이 원글 밑에 붙고, 늦게 달리면 글타래째 맨 아래로(끌어올리기), 글타래 전체가 가장 늦은 글 + 48h 에 함께 내려가는지.

### W4. 부담 · 과금 (7일)
- 하루 fxtwitter 호출 ≈ 7,200(분당 5) · 글 받은 실행 ≈ 280/일 예상 · GitHub 읽기 ≈ 550/일 · Groq 증가분(자기 답글 하루 2~3건분).
- Cloud Run `billable_instance_time`: 배포 전 30일 합계 약 54,900초(V0-3). 접수 서비스 하루 증가 ≈ 2,500초 이하 예상, 월 환산이 무료 18만 vCPU-초 안인지.
  ```bash
  # 최근 7일 서비스별(Monitoring API) — verify_result V0-3 와 같은 방법
  ```
- Scheduler 3잡 유지(무료 3개 — 지금까지 1개분 유료였던 것 해소).

### W5. 트윗 시트 실사용
- 운영자 폰(실제 터치): 플릭 전환 · 칩 줄 가로 스크롤 · 아래로 끌어 닫기 · 진동 · 엿보기(처음 2회) · 「여기부터 새 글」 흐름이 서로 방해하지 않는지(V6-9).
- 밝게 테마 · 움직임 줄이기 설정 화면(미확인).
- 새 동작: 읽음 처리가 **닫을 때 · 멤버 바꿀 때**(전엔 열 때) — 보드 배지가 그때 줄어드는 게 어색하지 않은지.

### W6. 기타 확인 필요
- 텔레그램 웹훅: 배포 때 `telegram_webhook.sh` 가 텔레그램 API 404(이 PC 의 `deploy/env.sh` 봇 토큰이 유효하지 않은 것으로 보임 — 실제 토큰은 Secret Manager). 접수 서비스 주소가 그대로라 기존 등록이 유지된다고 판단 — 운영자가 텔레그램에 `/status` 를 보내 응답이 오면 확인 끝. 이 PC 의 `env.sh` 토큰은 손볼 것.
- 원글 판정 규칙(§7-6, Claude 제안 — 운영자 미확인): 되살린 원글 = 판정 · DM 없음, 처음 들어오는 48h 안 원글 = 판정, 48h 넘은 원글 = 번역만.
- 보류: 트윗 시트 키보드 접근성(메모리 「키보드 접근성 보류」).
- 열린 PR: #100(버전 등급 문서) — 병합 대기.

## 되돌리기
1. Scheduler: `git show v4.8.6:deploy/scheduler.sh > /tmp/scheduler_v486.sh && bash /tmp/scheduler_v486.sh`(저장소 루트, `deploy/env.sh` 필요 · KST 05:50~06:30 피함) → 옛 4잡 생성 확인 → `gcloud scheduler jobs delete mewtype-daily mewtype-gapcheck --location=asia-northeast1`.
2. Cloud Run: `gcloud run services update-traffic mewtype-backend --to-revisions=mewtype-backend-00186-tms=100` · `mewtype-telegram` → `mewtype-telegram-00126-k8n=100`.
3. 프론트: `main` 에서 v4.9.0 병합 되돌리기 커밋(트윗 시트 → 옛 말풍선). 데이터는 하위호환(옛 코드는 `reply_to_id` 무시, 늘어난 `expires_at` 은 그대로 읽음).

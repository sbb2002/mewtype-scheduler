# 패치 명세 — 자기 답글 보완 (핫픽스, 2026-10-26 작성 · 미구현)

- 브랜치: `hotfix/self-reply-fill` (main `ddc2040` 에서 분기, 아직 커밋 없음)
- 버전: `hotfix/` 규칙대로 구현 · 병합 때 패치 번호(Z)를 올린다(그 시점 main 의 최근 기능 번호에 잇기). 번호는 병합 때 정한다.
- 상태: **명세만** — 코드는 아직 안 고쳤다. 아래 「코드 위치」 줄 번호는 main `ddc2040` 기준.
- 용어: 「빠진 트윗 보충」 · 「자기 답글」 = `docs/TERMINOLOGY.md` 「빠진 트윗 보충 용어 (v4.7.4)」.
  이 명세에서 새로 쓰는 말: **후속 확인*** — * 후속 확인 = 멤버 트윗 알림을 받은 뒤 5분 · 15분에 그 멤버의 최근 글 목록을 다시 조회해 빠진 트윗을 보충하는 예약 작업.
  구현하면 TERMINOLOGY 에 올린다.

## 1. 배경 (2026-10-26 확인한 사실)

- **자기 답글은 폰 알림으로 오지 않는다** — v4.7.4 실측 6건 중 0건. 서버에 들어오는 길은 빠진 트윗 보충뿐이다.
- **빠진 트윗 보충은 그 멤버의 다음 트윗 알림이 올 때만 돈다**(`telegram_app._fill_member_gaps`, `/ingest` 개인 트윗 분기 끝 7329줄).
  - 실례: 리츠 10-25 00:39 「✌️」(사진) → 폰 알림 정상 수신(00:47). 00:50 자기 답글 「仲町あられさん撮影📸📸📸」 → 폰 알림 없음.
    다음 글(15:20)의 알림을 계기로 15:24 에 보충됨 — **약 14.5시간 지연**. 다음 글이 48시간 안에 없었으면 영영 못 들어간다.
  - 최근 자기 답글: 아라레 10-23 21:54 · 노노카 10-24 13:34 · 리츠 10-25 00:50 (모두 지금은 들어와 있음). 원글과의 간격 = 노노카 1초 · 리츠 11분.
- **팬 화면에서 맥락이 없다** — `tweets.json` 항목에 원글 연결이 없고(`xtweet.parse` 출력에 답글 필드 없음), X 카드는 `hideThread=true`(`tweets.js` 214줄)라
  원글을 안 보여 준다. 말풍선 묶음은 시각 간격 2분 이내만 같은 묶음(`GROUP_GAP_MS`, `tweets.js` 26줄) — 리츠 사례(11분)는 따로 떨어져 「仲町あられさん撮影📸📸📸」만 보였다.
- **보충은 판정까지 같은 경로** — `_fill_member_gaps` → `_maybe_personal_tweet` → 그 안에서 `_maybe_personal_schedule` · `_maybe_broadcast_change`(3025 · 3028줄).
  늦게 들어오면 예고 · 변경 판정도 그만큼 늦다.
- **모니터 등급** — 보충 1건마다 `RESULT_WARN` 「gap-fill: 폰 알림이 빠진 트윗 보충」. 자기 답글은 늘 빠지는 게 정상이라 잡음이다.

## 2. 범위

| # | 내용 | 결정 |
|---|---|---|
| ① | 후속 확인 — 멤버 트윗 알림 수신 **5분 · 15분 뒤 두 번** 그 멤버 빠진 트윗 보충 실행 | 운영자 확정(2026-10-26) |
| ② | 자기 답글을 원글에 이어 붙여 표시 — `reply_to_id` 저장 + 프론트 묶음 | 진행 |
| ③ | 자기 답글 보충은 모니터 `ok` 로, 본인 일반 글 보충만 `warn` 유지 | 진행 |
| — | 1시간마다 5명 훑는 안전망 | **보류**(운영자 미결정) |
| — | 예고 판정 LLM 에 원글을 맥락으로 함께 넘기기 | **보류**(실사례 없음) |

fxtwitter 호출 한도: 운영자 판단 = 걱정 없음(코드 주석 `vxtwitter.fetch_profile_statuses` 에는 「IP 당 분당 1,000회(docs.fxembed.com)」로 적혀 있으나,
이번 추가 호출은 멤버 트윗 수 × 2 = 하루 수십 회라 어느 쪽이든 영향 없음).

## 3. ① 후속 확인 (5분 · 15분)

### 동작
- **언제 거나**: `/ingest` 개인 트윗 분기에서 `_maybe_personal_tweet` 이 끝난 뒤(지금 `_fill_member_gaps` 를 부르는 자리, 7327~7330줄).
  리트윗으로 건너뛴 알림(`retweet skip`)·테스트 계정(`force_echo`)·공식 계정 · 게임 계정 글은 걸지 않는다. 즉시 보충(지금의 `_fill_member_gaps` 호출)은 그대로 둔다.
- **기준 시각**: 알림을 **받은 시각**(`now_iso`) + 5분, + 15분. 두 건을 한 번에 예약한다.
- **실행**: 예약 시각에 `_fill_member_gaps(gh, channel_key, now_iso, exclude_tag=None)` 를 그대로 부른다(고르는 규칙 · 처리 경로 변경 없음).
  후속 확인이 보충한 트윗에서 다시 후속 확인을 걸지 않는다(보충 경로는 `/ingest` 분기를 안 타므로 자연히 안 걸림 — 구현 때 확인).
- **중복**: 같은 멤버 트윗이 짧은 간격으로 여러 개 오면 후속 확인도 여러 번 돈다. 비용은 fxtwitter 조회뿐이고(빠진 것이 없으면 쓰기 · LLM 없음),
  두 확인이 같은 빠진 트윗을 찾아도 앞 확인이 이미 커밋한 뒤라 뒤 확인은 `known` 으로 건너뛴다. 태스크 이름은 `gapchk-<멤버>-r<1|2>` + 예약 분(分) 버킷
  (`tasks._build_task` 기존 규칙) — 같은 분에 두 알림이 오면 하나로 합쳐진다.
- **실패**: 조회 실패 · 처리 실패는 지금처럼 아무것도 안 하고 끝(경로는 200 응답 — Cloud Tasks 재시도로 몰리지 않게). 예약 자체가 실패하면 로그만(알림 처리는 계속).
- **일시정지(`control.json` paused)**: 개인 트윗 인입이 paused 와 무관하게 도는 것과 맞춰 후속 확인도 그대로 돈다.

### 배선 (배포판)
- 보충은 외부 호출(fxtwitter · 번역 LLM)을 하므로 **접수 서비스(`mewtype-telegram`)에서 실행**한다 — 쓰기 서비스 `/write` 잡에서 돌리면
  「외부 호출은 접수 서비스에서 준비, `/write` 는 커밋만」(v3.7.1 A-1) 원칙이 깨진다.
- 새 경로 **`POST /gap-check`** (접수 서비스) — 본문 `{"channel_key": "...", "round": 1|2, "trigger_tag": "..."}`.
- 예약 = Cloud Tasks, 큐 `TASKS_QUEUE`(`mewtype-wake`), **대상 = 접수 서비스 자신의 URL**.
  지금 `tasks.from_env` 는 대상이 쓰기 서비스(`MAIN_SERVICE_URL`/`SERVICE_URL`)로 고정이라, 대상 URL 을 받는 생성 함수(또는 인자)를 더한다.
  접수 서비스 자기 URL = env `ADMIN_BASE_URL`(`deploy_telegram.sh` 가 `SELF_URL` 을 넣는다).
- **인증 — 확인 필요 사항 있음**: 접수 서비스는 `ALLOW_UNAUTH=1` 이라 `oidc.verify_request` 가 검증을 건너뛴다. `/gap-check` 는 공개 주소라
  OIDC 토큰을 **이 경로에서만 강제로** 검증해야 한다(audience = 접수 서비스 URL, 발급자 = `INVOKER_SA`). `verify_request` 에 강제 플래그를 더하는 방식을 제안.
  대안 = `/ingest` 처럼 공유 비밀 헤더. 어느 쪽이든 Cloud Tasks 의 `oidc_token` 설정(`_build_task`)은 그대로 쓸 수 있다.
- 실패해도 무해한 작업이라 큐 속도 제한(`WEBSUB_QUEUE`)은 쓰지 않는다.

### 배선 (로컬 시험판)
- 적용 큐(`q-apply`)에 넣으면 안 된다 — 보충 안에서 `writeclient.call_write` 가 적용 큐에 적재하고 결과를 기다리므로 같은 스레드에서 교착.
- **가공 큐(`q-enrich`)** 에 `run_at_iso` 를 주어 적재하고(`jobqueue.LocalQueue.enqueue`), `enrich.handle` 에 kind `gap_check` 를 더한다.

## 4. ② 자기 답글을 원글에 이어 붙이기

### 데이터 (계약 I `tweets.json` / `tweet_archive.json`)
- 항목에 **`reply_to_id`** 추가 — 그 트윗이 **같은 멤버 자기 글에 단 답글**이면 원글 tweet id(문자열), 아니면 `null`. 옛 항목엔 키가 없다(= `null` 취급).
- 값 출처(2026-10-26 실제 응답으로 확인):
  - 폰 경로: vxtwitter 단건 응답 `replyingTo`(핸들) · `replyingToID`(원글 id) → `vxtwitter.extract` 가 돌려주게 하고, `replyingTo` 가 그 멤버 핸들일 때만 채운다.
    fxtwitter 폴백 단건 응답은 `replying_to`(핸들) · `replying_to_status`(원글 id).
  - 빠진 트윗 보충: fxtwitter v2 목록 응답 `replying_to.status` → `vxtwitter.fetch_profile_statuses` 반환에 `reply_to_id` 추가.
- 전달: `_prepare_personal_tweet` → `xtweet.parse(..., reply_to_id=...)` → 커밋 함수(`/write` 잡 `personal_tweet`)가 그대로 저장. **쓰기 서비스 코드도 바뀐다**.

### 프론트 (`tweets.js` · `css/tweets.css`)
- `_groupMsgs`: 메시지의 `reply_to_id` 가 목록 안 다른 메시지의 `id` 면, 시각 간격과 상관없이 **원글이 든 묶음에 원글(또는 원글에 이미 붙은 답글) 바로 뒤로** 넣는다.
  원글이 목록에 없으면(48h 지나 내려감 · 삭제) 지금처럼 시각 순서대로 단독.
- 표시: 이어 붙은 메시지는 `.lane__thread__unit.is-reply` — 원글 쪽에 이어지는 연결선 + 번역 말풍선 머리표 「이어서」. 묶음 시각 표시는 지금처럼 묶음의 마지막 메시지.
  모양 세부는 구현 때 시안으로 확인.
- X 카드 `hideThread=true` 는 **유지** — 원글이 바로 위에 따로 있으므로 카드 안에 원글을 또 보이면 중복이다.
- 데이터는 지금처럼 `textContent` 로만(innerHTML 금지). 모바일 토스트 · PC 말풍선 공용(`_renderThread`).

## 5. ③ 모니터 등급

- `_fill_member_gaps` 에서 보충 후보 `s["reply_to"] == handle`(자기 답글)이면 `RESULT_OK` + detail 「gap-fill(자기 답글) · <id> · mode: …」,
  그 밖(본인 일반 글이 빠진 경우)은 지금처럼 `RESULT_WARN`. 모니터 결과 값은 `ok`/`warn`/`err` 셋뿐이라 「INFO」 대신 `ok` 를 쓴다.
- 후속 확인이 아무것도 못 찾은 경우는 기록하지 않는다(잡음). 후속 확인으로 보충한 건은 detail 에 「(후속 확인 r1|r2)」를 붙여, 몇 분 만에 잡혔는지 볼 수 있게 한다.

## 6. 같이 고칠 문서 · 점검

- `docs/SPEC.md` 계약 I(`reply_to_id`) · 「빠진 트윗 보충」 소절(후속 확인 · 등급) · §8.11 경로 목록(`/gap-check`) · §9 트윗 말풍선(이어 붙이기).
- `docs/TERMINOLOGY.md` 「후속 확인」 추가. `docs/VERSION.md` · README · CLAUDE.md 현재 버전 줄 · `config.js` `APP_VERSION`(병합 때, 「버전 올릴 때 할 일」).
- self-test: `xtweet`(parse 의 `reply_to_id`) · `vxtwitter`(extract · 목록 응답의 원글 id — fixture 갱신) · `telegram_app`(후속 확인 예약 2건 · 이름 규칙 ·
  리트윗/테스트 계정은 안 걸림 · `/gap-check` 인증 강제 · 등급 분기) · `tasks`(대상 URL 지정) · `enrich`(로컬 `gap_check`) · `render`/새 selfcheck(묶음 규칙 — 원글 있음/없음, 간격 11분).
- 배포: 접수 서비스 + 쓰기 서비스(커밋 데이터 모양이 바뀜) 둘 다 + 프론트(main 병합 시 Vercel). `setup.sh` 변경 없음(큐 · SA 재사용) — 구현 때 Tasks SA 가 접수 서비스 대상 토큰을 만들 수 있는지 확인.
- 실서비스 확인: 다음 자기 답글이 5분 또는 15분 확인에서 잡히는지(모니터 `gap-fill(자기 답글) … (후속 확인 r1)`) · 팬 화면에서 원글 아래 붙는지.

## 7. 확인 필요 (구현 전에 정할 것)

1. `/gap-check` 인증 방식 — OIDC 강제 검증(제안) / 공유 비밀 헤더.
2. 「이어서」 표시 모양 — 구현 때 시안.
3. 보류 2건(1시간 안전망 · 판정 맥락)은 이번 범위 밖 — 필요해지면 따로.

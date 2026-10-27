# 구현 명세 — 자기 답글 · 빠진 트윗 상시 조사 (핫픽스, 2026-10-27 3차 개정 · 미구현)

> 보류 해제 (2026-10-27) — 앞서 막던 `tweet_archive.json` 1MB 문제는 v4.8.6(보관함 캐시 · 일자 분리)으로 해결됐다. 이 명세로 구현한다.
> 검증 방법 · 합격 기준 = 같은 폴더 **`verify_spec.md`**. 둘을 같이 고친다.

- 브랜치: `hotfix/self-reply-fill` — 2026-10-27 main `f69a7bc`(v4.8.6) 로 다시 맞춤(그전 커밋 없음). 워크트리 `../mewtype-scheduler-worktrees/v4/hotfix-self-reply-fill`.
- 버전: `hotfix/` 규칙 — 병합 때 그 시점 main 의 최근 기능 번호에 패치 번호(Z)를 잇는다. 번호는 병합 때 정한다.
- 상태: **명세만**. 아래 줄 번호는 main `f69a7bc` 기준(구현 때 다시 확인).
- 개정 이력
  - 1차(10-26): 알림 5분 · 15분 뒤 후속 확인 → **폐기**(1시간 넘게 늦은 자기 답글 25% 를 못 잡음, §1).
  - 2차(10-26): 1분 상시 조사 · 원글 수명 규칙 · 중복 판정 방지.
  - 3차(10-27, 이 판): 과금 · 부담 점검 반영 — 운영자 결정 D6~D11(§2). X Activity API(유료 웹훅)는 검토 후 **반려**(§1-5).
  - v4.7.4 SPEC 의 「정기 수집에서는 안 함 — 운영자 결정 A안」은 이 패치로 바뀐다(운영자 10-26 · 10-27 결정).
- 용어: 「빠진 트윗 보충」 · 「자기 답글」 = `docs/TERMINOLOGY.md` 「빠진 트윗 보충 용어 (v4.7.4)」. 이 명세에서 새로 쓰는 말(구현하면 TERMINOLOGY 에 올린다):
  - **상시 조사*** — * 상시 조사 = 1분마다 멤버 5명의 최근 글 목록을 한 번씩 받아, 아직 안 들어온 본인 글(자기 답글 포함)을 찾는 예약 작업(`/gap-check`).
  - **보충 작업*** — * 보충 작업 = 상시 조사가 찾은 글 1건을 실제로 넣는 Cloud Tasks 작업(트윗 id 하나당 하나, `/gap-fill`).
  - **새 글 창*** — * 새 글 창 = 상시 조사가 「최근 N분 안에 새 글이 있나」 를 묻는 시간 폭. fxtwitter `since` 값 = 지금 − N분.
  - **이어 붙이기*** — * 이어 붙이기 = 자기 답글을 팬 화면 말풍선에서 원글 바로 뒤에 붙여 보이는 것.
  - **글타래 끌어올리기*** — * 글타래 끌어올리기 = 원글과 그 자기 답글들(글타래)을 말풍선 목록에서 「글타래의 가장 늦은 글」 시각 자리로 옮겨, 새 답글이 달린 글타래가 맨 아래(최신)에 오게 하는 것.
  - **일일 묶음 잡*** — * 일일 묶음 잡 = 매일 06:00~06:20 KST 에 따로 돌던 Cloud Scheduler 잡 3개(baseline · monitor · websub-renew)를 대신하는 잡 1개(`mewtype-daily`). 나머지 둘은 Cloud Tasks 로 예약한다.

## 1. 배경 (확인한 사실)

### 1-1. 지금 동작 (main `f69a7bc`)
- **자기 답글은 폰 알림으로 오지 않는다** — v4.7.4 실측 6건 중 0건. 서버에 들어오는 길은 빠진 트윗 보충뿐.
- **빠진 트윗 보충은 그 멤버의 다음 트윗 알림이 올 때만 돈다** — `telegram_app._fill_member_gaps`(2932줄), 호출 = `/ingest` 개인 트윗 분기 끝(7344줄).
  실례: 리츠 10-25 00:50 자기 답글 → 다음 글(15:20) 알림을 계기로 15:24 보충, **약 14.5시간 지연**.
- 보충 후보 규칙 = `xtweet.gap_candidates`(286줄): 본인 · 리트윗 아님 · 남에게 단 답글 아님 · 게시 48h 안 · 「이미 아는 id」(스레드 + 보관함 캐시) 아님 · 오래된 것부터 3건.
- **팬 화면에 맥락이 없다** — `tweets.json` 항목에 원글 연결이 없고, X 카드는 `hideThread=true`(`tweets.js` 214줄), 말풍선 묶음은 게시 시각 2분 이내만
  (`GROUP_GAP_MS` 26줄 · `_groupMsgs` 319줄). 리츠 사례(11분)는 답글만 따로 보였다.
- **보충은 판정까지 같은 경로** — `_maybe_personal_tweet`(2974줄) → 커밋 → `_maybe_personal_schedule`(3039줄) · `_maybe_broadcast_change`(3042줄).
  이 두 판정은 커밋 결과가 `dup`(같은 id 가 이미 있음 — `xtweet.merge_thread` 247줄)이어도 **다시 돈다**(§4-3).
- 트윗 보관함 캐시 `tweet_archive.json` 은 게시 7일(`archive_rotate.TWEET_KEEP_DAYS`)까지, 그 전은 일자 파일 `tweet_archive/<KST 날짜>.json`(`archive_rotate.read_day` 288줄).

### 1-2. 실측 — 자기 답글 (10-26, 이 폴더 `crawl.py` · `analyze.py` · `report.txt`)
- 자기 답글 **282건 / 원글 217개**(계정마다 조회 가능 범위 약 3~5.5개월). 원글 하나당 1개 156곳 · 2개 58곳 · 3개 2곳 · 4개 1곳.
- 원글과의 간격(중앙값 3.4분): 1분 이내 24% · 5분 이내 54% · 15분 이내 68% · 1시간 이내 75% · **1시간 넘음 25%**(최대 약 4.8일).
- 09-09 이후 자기 답글 65건 중 우리 데이터에 들어온 것 4건.
- 한계(확인 필요): 목록은 X 프로필 「게시물」 탭 기준 — 이 탭에 안 뜨는 형태의 자기 답글이 있다면 빠졌을 수 있다.

### 1-3. 실측 — 폰 알림 지연 · 글 수
- 받은 시각 − 게시 시각(827건): 중앙값 14초 · 2분 이내 64% · 5분 이내 76% · **10분 이내 87%** · 30분 이내 94%.
- 하루 본인 글(리트윗 제외): 09-15~10-26 평균 18.4건(자기 답글 실측분 포함), 최다 08-13 69건. 한 멤버 10분 안 최대 9건(유노).

### 1-4. 실측 — fxtwitter `/2/profile/<핸들>/statuses` (10-27, 5명 각 1회)
- **늘 약 20건**(20~21건, 리트윗 포함)을 준다. 문서상 `count`(1~100)가 있지만 `count=5` 로도 20건 — 개수는 못 줄인다.
- **`since` 는 거르지 않는다** — OpenAPI 원문: "returns 204 No Content if no posts in the page are newer than that instant; otherwise returns the normal JSON timeline".
  즉 「since 뒤 새 글이 없으면 204, 하나라도 있으면 20건 전체」. `since=지금` → 204 확인.
- 본인 글로 닿는 범위 1.5~6.5일(멤버마다 다름). 응답 77~110KB, 1.2~1.4초.
- 리트윗 항목의 `created_timestamp` 는 **원글 시각**이라 목록이 시각순이 아니다(본인 글끼리는 최신순). 리트윗은 어차피 후보가 아니다.
- `with_replies=1` 은 쓰지 않는다(10-26 실측: 리츠 자기 답글이 빠지고 남의 답글이 섞임). 기본 목록이 자기 답글을 준다.
- 한도: 문서 원문 "API v2 has a rate limit of 1000 requests per minute … per IP address" — **하루 한도는 문서에 없고 응답 헤더에도 한도 표시 없음**(확인 불가).

### 1-5. 과금 점검 (10-27)
- **Cloud Scheduler**: 요금표 원문 "Each Google billing account gets 3 jobs per month free … measured at the account level". 그 위는 잡당 $0.10/31일, 실행 횟수 무관, 일시정지 잡도 1개.
  결제 계정(`01952B-…`)의 프로젝트 4개 중 잡이 있는 곳은 `mewtype-scheduler` 하나 — **지금 4잡 = 계산상 1개 유료**(실제 청구서는 콘솔 확인 필요).
- **Cloud Run**(요청 기반 과금, 두 서비스 모두 CPU 상시 할당 없음 · 1 vCPU · 512Mi): 최근 30일 `billable_instance_time` 합계 약 54,900초
  (backend 38,077 · telegram 16,339 · 스테이징 474). 무료 = 월 18만 vCPU-초 · 36만 GiB-초 · 200만 요청(결제 계정 합산). 쉬는 인스턴스는 과금 안 됨.
- **Cloud Tasks**: 월 100만 작업 무료(계정 단위). **Cloud Logging**: 프로젝트당 월 50GiB 무료.
- **X Activity API**(`post.create` 웹훅 — 자기 답글을 능동으로 받는 유일한 공식 수단): 이벤트당 $0.005, 월 약 $5 추정 → **운영자 반려**(팬 메이드 · 수익 없음, 과금이 생기면 유지 곤란).

## 2. 결정 (운영자 확정)

| # | 날짜 | 내용 |
|---|---|---|
| D1 | 10-26 | **상시 조사 1분** — 멤버마다 최근 글 목록 1회(실행당 5회). 1차의 5분 · 15분 후속 확인은 폐기 |
| D2 | 10-26 | 조사 대상 = 본인 글 중 **리트윗 아님 · 남에게 단 답글 아님 · 아직 미등록** — 자기 답글과 본인 일반 글(폰 알림이 빠진 것) 둘 다 |
| D3 | 10-26 | **자기 답글이 달리면 원글 수명 = max(원글 게시 + 48h, 답글 게시 + 24h)**. 원글이 미등록이면 원글을 넣고/되살리고 같은 규칙 |
| D4 | 10-26 | 자기 답글을 원글에 이어 붙여 표시(`reply_to_id` + 프론트 묶음) |
| D5 | 10-26 | 모니터 등급: 자기 답글 보충 = `ok`, 본인 일반 글 보충 = `warn` |
| D6 | 10-27 | **Scheduler 잡을 3개 안으로** — 매일 잡 3개를 일일 묶음 잡 1개로 합치고(§4-6), 상시 조사 잡을 더해 총 3개(무료). 지금 내는 1개분도 없어진다 |
| D7 | 10-27 | **새 글 창 5분**(2차의 30분 → 5분). 회복은 매시 정각 실행(`since` 없이 20건)이 맡는다 |
| D8 | 10-27 | **본인 일반 글은 게시 10분 뒤부터 후보**(2차의 2분 → 10분, 폰 알림 87% 가 먼저 옴). 자기 답글은 바로 후보 |
| D9 | 10-27 | **조사 시간 상한 + 연속 실패 시 쉬기**(§4-1 ⑥) — fxtwitter 장애가 Cloud Run 무료 사용량을 잡아먹지 않게 |
| D10 | 10-27 | **스테이징에는 Scheduler 잡을 만들지 않는다** — 스테이징 시험은 수동 호출로만 |
| D11 | 10-27 | 화면 = 이어 붙이기 + **글타래 끌어올리기**(§4-4). 모양(연결선 · 표시 문구)은 구현 때 시안을 보고 운영자가 다시 정한다 |

## 3. 데이터 (계약 I `tweets.json` / `tweet_archive.json` · 일자 파일)

- 항목에 **`reply_to_id`**: 같은 멤버 자기 글에 단 답글이면 바로 위 글의 tweet id(문자열), 아니면 `null`. 옛 항목엔 키가 없다(= `null`). `xtweet._ROW_KEYS` 에 더한다.
  - 폰 경로: vxtwitter 단건 `replyingTo`(핸들) · `replyingToID` / fxtwitter 폴백(`vxtwitter.fetch_tweet_fx` 118줄) `replying_to` · `replying_to_status` — **핸들이 그 멤버일 때만**.
    (확인 필요: vxtwitter 단건 응답의 실제 키 이름 — 구현 때 실응답 1건으로 확인 후 fixture 에 넣는다.)
  - 상시 조사: fxtwitter 목록 `replying_to.status` → `vxtwitter.fetch_profile_statuses`(158줄) 반환에 `reply_to_id` 추가(지금은 `reply_to` 핸들만).
- **수명**(지금 `expires_at = 게시 + 48h`, `xtweet.TTL_HOURS` 35줄): 자기 답글을 커밋하는 같은 커밋에서 **원글(사슬이면 뿌리까지 전부)** 의
  `expires_at = max(지금 값, 원글 게시 + 48h, 답글 게시 + 24h)`. 답글 자신은 게시 + 48h 그대로.
  - 예: 원글 10:00 · 답글 10:05 → 원글 그대로. 원글 10-01 · 답글 10-04 → 원글 10-05 까지.
- **원글 되살리기**: 원글이 스레드에 없고 보관함에 있으면(`archived_reason` = `expired` · `rolled` · `replaced`) 스레드로 되살린다(번역 재사용, 보관함에서 지움).
  - 찾는 곳: 캐시 `tweet_archive.json`(게시 7일 안) → 없으면 일자 파일 `tweet_archive/<원글 게시 KST 날짜>.json`(`archive_rotate.read_day`, 날짜 = tweet id 로 계산 `archive_rotate.tweet_day`).
    일자 파일에서 되살리면 그 일자 파일에서도 지운다(캐시 · 일자 파일 양쪽에 남지 않게 — v4.8.6 「잃은 항목 0 · 중복 0」 규칙 유지).
  - `deleted`(관리 페이지 · `/del tweet` 으로 지움, `_tweet_del_commit` 6288줄)면 되살리지 않고 **답글도 올리지 않는다** — 기본값, 확인 필요(§7-1).
- 스레드 상한 `MAX_THREAD = 50`(199줄) 그대로. 되살린 원글이 바로 밀려나면(`rolled`) 이어 붙이기는 원글 없이 답글 단독 표시로 떨어진다.
- 글타래 끌어올리기는 **데이터를 바꾸지 않는다** — 저장 순서는 지금처럼 게시 시각순(`xtweet._sort_key` 223줄), 자리 옮기기는 프론트가 한다(§4-4).

## 4. 동작

### 4-1. 상시 조사 — 접수 서비스 `POST /gap-check` (1분, Scheduler `mewtype-gapcheck`)
1. **OIDC 강제 검증**(§5-3) — 실패면 403, 외부 호출 없음.
2. 멤버 5명 동시에 `GET /2/profile/<핸들>/statuses?since=<지금 − 5분, Unix 초>`(D7). 호출마다 타임아웃 4초(`FX_TIMEOUT_SEC` 41줄 그대로).
   - **매시 정각(KST 분 = 0) 실행만 `since` 없이**(20건) — 장애 · 지연으로 새 글 창을 놓친 글 회복, 그리고 D8 의 10분 대기를 넘긴 일반 글을 잡는 자리.
3. **5명 모두 204 면 바로 끝** — GitHub 읽기 · 쓰기 · LLM · 모니터 기록 없음(대부분의 실행).
4. 응답이 있으면 `tweets.json` + `tweet_archive.json`(캐시) 를 한 번 읽어 「이미 아는 id」 를 빼고 후보를 고른다(`xtweet.gap_candidates` 를 고침):
   - 개수 상한 3건 → 없앤다(실행 간격이 짧아 한 번에 몰리지 않는다).
   - **본인 일반 글은 게시 10분 뒤부터 후보**(D8). **자기 답글은 바로 후보**.
   - 자기 답글의 원글이 48h 를 넘었어도 답글은 후보 — 원글은 §4-2 가 찾는다.
   - 결과: 일반 글(폰이 빠뜨린 것)은 새 글 창(5분) 안에서는 아직 10분이 안 돼 후보가 안 되고 **다음 정각 실행에서 보충**된다(게시 후 10~70분). 자기 답글은 다음 실행(≤ 약 1분).
5. 후보마다 **보충 작업**을 큐 `mewtype-gapfill` 에 적재 — 이름 `gapfill-<트윗 id>`(분 버킷 없이, §5-2). 이미 같은 이름이면 `AlreadyExists` → 건너뜀.
6. **시간 상한 · 쉬기(D9)**:
   - 조사 1회 전체 상한 20초(GitHub 읽기 포함). 넘으면 그 자리에서 끝내고 다음 실행에 맡긴다.
   - **5명 호출이 모두 실패**(타임아웃 · 5xx · 연결 실패)한 실행이 **3번 연속**이거나 **한 번이라도 429** 면 → 이후 10분 동안 조사를 건너뛴다(실행은 오되 바로 200).
     상태는 인스턴스 메모리에 둔다(GitHub 쓰기 없음). 새 인스턴스가 뜨면 0 부터 — 최악이면 3회 더 시험하고 다시 쉰다(허용).
   - 쉬기 시작 · 끝은 모니터에 `warn` 1줄씩(「gap-check: fxtwitter 연속 실패 — 10분 쉼」 / 「재개」). 쉬는 동안 실행은 기록하지 않는다.
   - 효과(계산): fxtwitter 가 하루 종일 타임아웃이어도 13분에 3회 × 약 4초 → 하루 약 1,330초(쉬기 없으면 약 5,900초).
7. 번역 · 판정 LLM 은 **보충 작업에서만** 돈다.

### 4-2. 보충 작업 — 접수 서비스 `POST /gap-fill` (트윗 1건, 큐 `mewtype-gapfill`)
- 큐: `max-concurrent-dispatches=1`(보충끼리 동시에 안 돎 — 같은 글 두 번 처리 · 쓰기 몰림 방지) · `max-attempts=3`.
1. OIDC 강제 검증(§5-3).
2. `tweets.json` 을 다시 읽어 이미 등록이면 끝(폰이 먼저 넣은 경우) — 200.
3. 자기 답글이면 원글부터:
   - 원글이 스레드에 있음 → 다음 단계.
   - 보관함(캐시 → 일자 파일)에 있음(`deleted` 제외) → 되살림(§3).
   - `deleted` → 답글도 올리지 않고 끝(모니터 `ok` 「gap-fill skip: 원글 삭제됨」).
   - 어디에도 없음 → fxtwitter `/2/thread/<원글 id>`(또는 단건 조회)로 원글 본문을 받아 **같은 개인 트윗 경로로 먼저 넣는다**(원글이 또 자기 답글이면 뿌리까지 위로, 최대 5단).
     원글이 48h 를 넘었어도 넣는다(수명은 §3 규칙으로 답글 게시 + 24h).
4. 그 글을 `_maybe_personal_tweet(..., via="gapfill", reply_to_id=...)` 로 — 번역 · 예고 판정 · 변경 판정까지 지금 경로 그대로.
5. 실패하면 200 으로 끝내고(재시도 폭주 방지) 다음 상시 조사가 다시 찾는다. 태스크 이름이 막혀 있는 동안(§5-2)은 「이미 적재」로 건너뛰고, 풀리면 다시 적재.

### 4-3. 폰 알림과 겹칠 때 — `_maybe_personal_tweet` 고침
- **커밋 결과가 `dup` 또는 `stale` 이고 `via != "ops"` 면 예고 판정 · 변경 판정 · 새 트윗 DM 을 건너뛴다.** 관리 페이지 수동 경로(`via="ops"`)는 지금처럼 돈다.
  - 지금은 `dup` 이어도 `_maybe_personal_schedule` · `_maybe_broadcast_change` 가 돈다 → 같은 글을 두 번 판정(Groq 두 배 · 중복 DM 위험).
- 준비 단계는 이미 「바뀐 게 없으면 번역 안 함」(`_prepare_personal_tweet` 2014줄, 2037~2038줄에서 스레드 · 보관함을 읽음) — 둘이 거의 동시에 준비하면 번역만 두 번 될 수 있다(드묾, 허용).
- **`/ingest` 의 즉시 보충 호출(7344줄 `_fill_member_gaps`)은 없앤다** — 상시 조사가 같은 일을 한다. `_fill_member_gaps` 함수는 상시 조사 쪽으로 옮겨 다시 쓴다(이름 · 위치는 구현 때).
- `via` 값 `"gapfill"` 을 새로 쓴다 — 모니터 리포트 · 웹 모니터가 모르는 `via` 값을 어떻게 그리는지 구현 때 확인(`monitor_report`). 문제가 있으면 `"ingest"` + detail 로 구분.

### 4-4. 이어 붙이기 · 글타래 끌어올리기 — 프론트 (`tweets.js` · `css/tweets.css`)
- `_visible`(111줄) 다음, `_groupMsgs`(319줄) 앞에서 **글타래**를 만든다: `reply_to_id` 가 목록 안 다른 메시지의 `id` 면 같은 글타래(사슬은 뿌리까지).
  - 글타래 안 순서 = 게시 시각순(원글 → 답글 → 답글의 답글).
  - **글타래의 목록 자리 = 글타래 안 가장 늦은 글의 게시 시각**(끌어올리기, D11) — 몇 시간 뒤 답글이 달리면 원글째 맨 아래(최신)로 온다. 말풍선은 열면 맨 아래로 스크롤되므로(`_renderThread` 354줄) 새 답글이 바로 보인다.
  - 원글이 목록에 없으면(만료 · 밀려남 · 삭제) 답글은 지금처럼 단독.
- 글타래는 2분 묶음(`GROUP_GAP_MS`)과 따로 — 글타래 하나가 한 묶음, 묶음 시각 표시는 가장 늦은 글 기준.
- 답글 유닛 `.lane__thread__unit.is-reply` — 원글 쪽 연결선 + 표시 문구(「이어서」 등). **모양은 시안으로 운영자 확인 후 확정**(D11).
- X 카드 `hideThread=true` 유지(원글이 바로 위에 따로 있으므로). 데이터는 `textContent` 로만(innerHTML 금지 규칙). PC 말풍선 · 모바일 토스트 공용.
- 읽음 · 안 읽은 개수(`_readMap` · 배지)는 id 단위 그대로 — 끌어올려진 원글은 이미 읽음이면 읽음 유지, 새 답글만 안 읽음.

### 4-5. 모니터
- 보충 1건마다: 자기 답글 = `ok` 「gap-fill(자기 답글) · <id> · +N분 · mode: …」, 본인 일반 글 = `warn` 「gap-fill · <id> · +N분 · mode: …」
  (+N분 = 게시 → 들어오기까지). 원글을 같이 넣었으면 「원글 함께」, 되살렸으면 「원글 되살림」.
- 상시 조사가 아무것도 못 찾은 실행 · 204 실행은 기록하지 않는다. 쉬기 시작 · 끝만 기록(§4-1 ⑥).

### 4-6. 일일 묶음 잡 — 쓰기 서비스 `POST /daily` (D6)
- Scheduler `mewtype-daily` — `0 6 * * *` `Asia/Seoul`(지금 baseline 은 `Asia/Tokyo` 06:00 — 같은 UTC+9 라 시각이 같다). OIDC = `INVOKER_SA`, audience = 쓰기 서비스 URL.
1. OIDC 검증(쓰기 서비스는 지금처럼 `_authorize`).
2. **먼저** 새 큐 `mewtype-daily` 에 두 작업을 예약 — `/monitor` 를 **그날 KST 06:10**, `/websub-renew` 를 **그날 KST 06:20**(본문 `{}`).
   - 예약 시각을 「그날 06:10 · 06:20」 고정값으로 계산하므로 태스크 이름(`daily-monitor-<분 버킷>` · `daily-websub-renew-<분 버킷>`, `tasks._build_task` 34줄 규칙)이 재시도해도 같다 → 중복 예약은 `AlreadyExists` 로 막힌다.
   - Scheduler 재시도(최대 3회 · 30~300초)가 06:10 뒤에 와도 예약 시각이 지난 작업은 바로 실행되고, 이미 실행된 이름은 다시 못 만든다(§5-2) → monitor DM 은 하루 1번.
3. 그다음 baseline tick 을 그대로 실행(`handlers.tick("baseline")` — 지금 `/tick {"mode":"baseline"}` 와 같은 코드, 일시정지 가드 포함). 결과 · 오류 처리도 `/tick` 과 같다.
- `/monitor` · `/websub-renew` 라우트는 그대로(본문 · 동작 불변). 부르는 쪽만 Scheduler → Cloud Tasks 로 바뀐다.
- 순서 보장: monitor 가 baseline 뒤에 와야 한다(`deploy/scheduler.sh` 주석 — 09-16 빈 리포트 사고). 06:10 예약이라 지금과 같다. 쓰기 서비스는 동시 1 이라 겹쳐도 차례로 처리.
- 큐 `mewtype-daily`: `max-concurrent-dispatches=1 · max-attempts=4 · min-backoff=30s · max-backoff=300s`(지금 Scheduler 잡의 「재시도 3회 · 30~300초」와 같게).
  기존 wake 큐(`mewtype-wake`)를 쓰지 않는 이유 = 그 큐는 최대 시도 횟수를 정하지 않아(기본값) `/monitor` 가 계속 실패하면 오류 DM 이 여러 번 갈 수 있다.
- 로컬 시험판(`local_runner`)은 자체 타이머라 이 변경과 무관 — 손대지 않는다.

## 5. 배선

### 5-1. Scheduler (바뀐 뒤 3개 = 무료)

| 잡 | 일정 | 대상 |
|---|---|---|
| `mewtype-light` | `*/10 * * * *` UTC | 쓰기 서비스 `/tick {"mode":"light"}` (그대로) |
| `mewtype-daily` (새) | `0 6 * * *` Asia/Seoul | 쓰기 서비스 `/daily` |
| `mewtype-gapcheck` (새) | `* * * * *` | 접수 서비스 `/gap-check` (audience = 접수 서비스 URL) |

- 지울 잡: `mewtype-baseline` · `mewtype-monitor` · `mewtype-websub-renew`.
- `deploy/scheduler.sh`: 새 잡 둘을 만든 **뒤** 옛 잡 셋을 지운다(같은 날 두 벌이 돌면 monitor DM 두 번). **KST 05:50~06:30 에는 돌리지 않는다**(스크립트가 시각을 보고 거부).
  접수 서비스 URL 은 `TELEGRAM_SERVICE`(기본 `mewtype-telegram`)로 조회. `upsert_job` 에 audience 인자를 더한다(지금은 쓰기 서비스 URL 고정).
- **`STAGE=1` 이면 `scheduler.sh` 는 아무것도 안 하고 끝낸다**(D10). 참고: 지금 스크립트는 `STAGE=1` 에서도 같은 잡 이름(`mewtype-*`)을 스테이징 URL 로 덮어쓸 수 있는 구조다 — 이번에 막는다.

### 5-2. Cloud Tasks
- 새 큐 `mewtype-gapfill`(`--max-concurrent-dispatches=1 --max-attempts=3`) · `mewtype-daily`(§4-6). `deploy/setup.sh` 에 추가(멱등, 생성 · 갱신 모두 옵션 강제 — 기존 큐와 같은 방식).
  스테이징 = `mewtype-gapfill-stage` · `mewtype-daily-stage`(`deploy/env.stage.sh` 에 `GAPFILL_QUEUE` · `DAILY_QUEUE`).
- 대상: 보충 작업 = 접수 서비스 자신(env `ADMIN_BASE_URL` = 자기 URL), 일일 작업 = 쓰기 서비스(`SERVICE_URL`).
  `tasks.from_env`(99줄)는 대상이 쓰기 서비스로 고정 → **대상 URL 을 받는 인자**를 더한다. 범용 적재 메서드(`enqueue_path(path, body, name_key, schedule_time_iso)`)를 더한다.
- 보충 작업 이름 `gapfill-<id>` 는 분 버킷 없이 — `_build_task` 에 「버킷 안 붙임」 선택지를 더한다(기존 wake · tick · write 이름 규칙은 그대로).
- 같은 이름은 실행 · 삭제 뒤 한동안 다시 못 만든다(문서마다 1h/4h/24h 로 달라 확인 필요 — 보충은 그 동안 「이미 등록」 검사가 막으므로 결과는 같음).

### 5-3. 인증
- 접수 서비스는 `ALLOW_UNAUTH=1` 이라 `oidc.verify_request`(20줄)가 검증을 건너뛴다. `/gap-check` · `/gap-fill` 은 공개 주소이므로
  **이 두 경로만 강제 검증** — `verify_request(..., force=True)` 인자 추가(audience = 접수 서비스 URL, 발급자 = `INVOKER_SA`). 기존 공개 경로(`/telegram` · `/ingest` · `/websub/*` · `/admin` · `/monitor-live`)는 그대로.
- 검증 실패면 403 — fxtwitter · GitHub 호출 전에 끝낸다(남이 불러 사용량을 늘리는 것 방지).

### 5-4. 일시정지(`control.json` paused)
- 상시 조사 · 보충 작업: 개인 트윗 인입처럼 **상관없이 돈다**. 일일 묶음 잡: baseline tick 은 지금처럼 일시정지 가드를 따르고, monitor · websub-renew 도 지금처럼 가드 없음.

### 5-5. 로컬 시험판
- Scheduler 대신 로컬 러너 타이머 1분 → 상시 조사. 보충 작업은 **가공 큐(`q-enrich`)** 에 적재(적용 큐 `q-apply` 에 넣으면 `call_write` 가 같은 큐를 기다려 교착).

## 6. 부담 · 과금 (예상)

| 항목 | 예상 | 근거 |
|---|---|---|
| Scheduler | 잡 3개 = 무료(지금 월 $0.10 → $0) | §5-1 |
| fxtwitter | 하루 7,200회(분당 5회, 한도 0.5%) · 글을 받는 호출 하루 평균 약 80회 + 정각 120회 · 받는 데이터 하루 약 19MB | 09-15~10-26 게시 시각 모의 계산 |
| Cloud Run(접수) | 하루 1,440회 실행 · 월 약 7.5만 vCPU-초 추가(지금 5.5만과 합쳐 약 13만 / 무료 18만). fxtwitter 장애 땐 쉬기로 월 약 4만 이하 | §1-5 · §4-1 ⑥ |
| Cloud Tasks | 보충 하루 몇 건 + 일일 2건 · 무료 100만 회 안 | |
| GitHub 읽기 | 글을 받은 실행마다 2회(하루 약 400회) · PAT 시간당 5,000 | |
| Groq | 자기 답글 하루 약 2~3건분 번역 · 판정 추가. §4-3 으로 중복 판정은 줄어듦 | 공유 키 TPD 주의(메모리 「Groq 공유 키 한도」) |
| `/write` | 보충 동시 1건 — 몰릴 때(4건 일괄 등) 차례로. 그동안 tick · wake 가 몇 초 밀릴 수 있음 | |

## 7. 확인 필요 (구현 전 · 중에 정할 것)
1. **원글이 관리 페이지에서 지워진(`deleted`) 자기 답글** — 답글도 안 올림(기본값) / 답글만 단독으로 올림.
2. 「이어서」 표시 모양 · 연결선 — 구현 때 시안(PC · 모바일 · 밝게/어둡게)으로 운영자 확인(D11).
3. 일반 글(폰이 빠뜨린 것) 보충이 **다음 정각까지(게시 후 10~70분) 늦어지는 것** 이 괜찮은지 — 지금(다음 트윗 알림 때)보다는 빠르다. 더 빨라야 하면 정각 실행을 15분마다로(정각 실행 하루 120 → 480회).
4. vxtwitter 단건 응답의 답글 키 이름(§3) · fxtwitter `/2/thread` 응답 모양 — 실응답으로 확인 후 fixture.
5. 모니터 리포트 · 웹 모니터의 새 `via="gapfill"` 처리(§4-3).

## 8. 배포 순서 · 되돌리기
- 순서: `setup.sh`(큐 2개) → `deploy.sh`(쓰기 서비스: `/daily` · 데이터 모양 · 수명 규칙) → `deploy_telegram.sh`(접수: `/gap-check` · `/gap-fill` · §4-3) →
  스테이징 수동 시험(`verify_spec.md` V3) → `scheduler.sh`(KST 05:50~06:30 피해서 — 새 잡 2개 만들고 옛 잡 3개 지움) → main 병합 시 Vercel(프론트).
- 두 서비스 공통 코드(`telegram_app.py` · `writers.py` 등)를 바꾸므로 `deploy.sh` + `deploy_telegram.sh` 둘 다.
- 되돌리기: Scheduler 는 옛 `scheduler.sh`(main 의 지금 판)로 옛 잡 3개를 다시 만들고 `mewtype-daily` · `mewtype-gapcheck` 를 지운다(이 순서 — monitor 가 하루 빠지지 않게).
  Cloud Run 은 직전 리비전으로 트래픽(배포 때 VERSION.md 에 적음). 옛 코드는 `reply_to_id` 를 모르는 키로 무시하고, 늘어난 `expires_at` 은 그대로 읽는다(계약 하위호환).

## 9. 같이 고칠 문서
- `docs/SPEC.md`: 계약 I(`reply_to_id` · 수명 규칙 · 되살리기) · 「빠진 트윗 보충」 소절(상시 조사 · 보충 작업 · 등급 · 즉시 보충 제거 · 「정기 수집 안 함」 문구 교체) ·
  §8.11 경로(`/gap-check` · `/gap-fill`) · 쓰기 서비스 `/daily` · §9 트윗 말풍선(이어 붙이기 · 끌어올리기) · §12 인프라(Scheduler 3잡 · 큐 4개).
- `docs/TERMINOLOGY.md`: 상시 조사 · 보충 작업 · 새 글 창 · 이어 붙이기 · 글타래 끌어올리기 · 일일 묶음 잡.
- `CLAUDE.md` 「인프라」(Scheduler 잡 · 큐 목록) · 「데이터 흐름」 3. `deploy/README.md`. 병합 때 `docs/VERSION.md` · README · `config.js` `APP_VERSION`.

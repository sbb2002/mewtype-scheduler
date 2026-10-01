# v4a 결정 로그 — `v4a_idea.md` 검토 (2026-09-29)

`v4a_idea.md`(v4a 요약 기능 목록)를 현행 코드와 대조한 뒤 사용자가 확정한 사항.
"현행" 서술은 이 세션에서 코드를 직접 읽거나 실행해 확인한 것만 적었다(근거 표기).
미구현 — 설계 입력 자료. 상위 설계는 `v4a_design.md`.

## 1. 확정 사항

### 1-1. preview 상태(FSM)

| # | 결정 | 현행 (근거) |
|---|---|---|
| D1 | **live 진입 = 업스트림 YT 알림(주) + `videos.list` 폴링(안전망)** 병행 | 폴링만으로 live 판정. 공개 방송 YT 알림은 즉시 wake 1개 예약만 한다 (`telegram_app._handle_yt_relay`) |
| D2 | **watching 진입 = 예고 시각 20분 전, 또는 YT "30분 전" 알림 수신 시** | 예고 시각 3분 전 (`statemachine.PRELIVE_LEAD_SEC=180`) |
| D3 | **URL 없는 announced**: YT 30분 전 알림이 예고 시각 **±45분** 안이면 그 알림의 URL 로 갱신 후 watching | assumed-live 폴백·watching 지각 강등(120분) 규칙으로 처리 |
| D4 | URL 없는 announced 에 알림이 안 오면: **시작 +2분에 `search.list` 1회** 확인. **예고 +1h 까지 live 못 오르면 out** | `expires_at`(예고 +3h) TTL 로 아카이브 |
| D5 | assumed-live / watching 지각 강등 **폐지** (D3·D4 로 대체) | `statemachine` 규칙 3·4 |
| D6 | **end 후 같은 영상이 다시 live 로 관측되면 live 복구** | 복구 안 됨 — end 에 머묾 (시뮬레이션 확인: end 아이템 + `live_state="live"` → `end-check`). 복구 규칙 9(`preview_stream_seen`)는 호출부가 없어 사장됨 |
| D7 | **상태 `none` → `out` 으로 개명.** 역할(아카이브 이관 신호)은 유지 | `none` 은 `preview.json` 에 저장되지 않고 `preview_archive.json` 이관 신호로만 쓰임 (`end→none`·removed·TTL·assumed-live drop) |
| D8 | 용어 `out` 을 `docs/TERMINOLOGY.md` 에 등록 (사용자 승인) | — |

- end 판정 자체는 현행 유지: 폴링에서 `liveBroadcastContent="none"` → end, 30분간 5분 간격 확인 후 out.

### 1-2. 프론트 표시

| # | 결정 |
|---|---|
| D9 | 레인에 **live 인 영상이 있으면 end 카드보다 우선해 ON-AIR 영역에 표시.** 합동방송 레인도 동일. 계기: 유노가 본방 종료 직후 회원 방송을 이어 진행한 사례 |
| D10 | end 카드는 "방송 종료" 표시 (현행과 같음 — `render.js`) |

- 현행 레인 안 카드 정렬 로직은 **확인 필요**(이번 검토에서 안 읽음).

### 1-3. 예고 판정

| # | 결정 | 현행 |
|---|---|---|
| D11 | 공식 트윗 = **정규식** 파싱 (서식이 정형화돼 있음) | 정규식 (`xrelay`) |
| D12 | 개인 트윗 = **정규식 + LLM 최종 확인**. 합동방송은 특히 LLM 확인 중요 | URL 없을 때 정규식 + `announces_own_broadcast`, 외부 채널은 `participation` |
| D13 | 공식 트윗에 영상 URL 이 있으면 **즉시 `videos.list` 로 확인해 upcoming 등록** (URL = 멤버 채널 URL 이 아닌 영상 URL) | `video_id` 포함 announced 로 등록 → 다음 tick(최대 10분)에 승격. 개인 트윗은 v3.6 부터 이미 즉시 확인 |
| D14 | upcoming 필수 요소 = URL·날짜·제목 | 시각(미정 아님)·제목·썸네일·URL·`video_id` (`preview.promote_state`) |

### 1-4. 썸네일

| # | 결정 | 현행 |
|---|---|---|
| D15 | **개인 트윗이 주는 썸네일은 받지 않는다.** 썸네일은 URL 확보 후 `videos.list` 에서만 | 이미 `videos.list`(`_select_thumbnail`: maxres>standard>high>medium>default) 한 곳뿐. `ytnotif.parse_yt_notif` 의 mqdefault 경로는 호출부 없음 |

### 1-5. 소식·트윗

| # | 결정 | 현행 |
|---|---|---|
| D16 | 소식: 리트윗 **제외** | 등록됨 — 소식 93건 중 24건이 `src_handle="RT @…"` (2026-09-29 데이터) |
| D17 | 개인 트윗: 리트윗 제외 | 이미 제외 (`xtweet.parse`) |
| D18 | 트윗 보존 24h → **48h** | `xtweet.TTL_HOURS = 24` |
| D19 | **스케줄 관련 트윗 원문 보존** | 공식 스케줄 트윗 원문은 어디에도 저장 안 됨(파싱 결과만 preview 로). 흔적은 `monitoring` 이벤트 로그 `flow="relay"` 뿐 |

### 1-6. 현행 유지 (요약에서 빠졌지만 그대로 가져갈 것)

| # | 항목 |
|---|---|
| D20 | 회원 전용 방송 감지: YT 알림 → yt-dlp 로 `video_id` 확보. 종료는 `videos.list` 폴링 (2026-09-20 유노 `wPWZblyvzDc` 가 이 경로로 정상 end→아카이브, `api_start_seen` 기록됨) |
| D21 | 콜라보 참여 판정 (외부 채널 LLM `participation` 등) |
| D22 | 비유튜브 URL(bilibili 등) 방송 → 소식으로 이관 |

### 1-7. 부가 기능

| # | 결정 |
|---|---|
| D23 | 모니터링 시스템 현행 유지 |
| D24 | 제어: 관리자 웹 UI 로 기존 DM 명령(ingest·edit·del 등) 수행. DM 은 status·pause·resume·list 등만 유지 |

### 1-8. 보류

| # | 결정 |
|---|---|
| D25 | **데이터 저장소 → DB(Supabase) 이관: 보류** ("지금은 없던 걸로"). 검토 내용은 §3 |

### 1-9. 2차 검증 후속 결정 (2026-10-01, `v4a_remaining_0930.md` §1)

| # | 결정 | 구현(v4a) |
|---|---|---|
| D26 | **프리미어 제외는 그룹 공식 채널만.** 멤버 개인 채널 프리미어(퀴즈 · 기념 영상 · 커버 등)는 방송 카드로 올린다. 09-30 엔 채널 무관 전부 뺐다 — 첫 실례가 노노카 「このエピソード夢？現実？クイズ」(10-01 18:00 KST, 프리미어, 카테고리 24) | `preview_build.is_group_release` — 수집 · 공식 스케줄 영상 확인 · 멤버 트윗 URL · 관리 페이지 URL 4곳이 공용. 카테고리로는 못 가른다(그룹 채널은 싱글 무비 · 생방송 · 라디오가 전부 24, 10-01 실측) |
| D27 | 영상이 있는 예고의 시각 변경(LLM 자동 · 관리 페이지)이 다음 수집에서 API 시각으로 돌아가는 것 = **현행 유지**(YouTube API 가 진실) | 코드 변경 없음. 하네스 B5 를 의도된 동작으로 고침 |
| D28 | 멤버가 **공식 일일 스케줄을 인용**한 글의 영상 URL 이 본문엔 없고 인용문에만 있으면 **작성자를 게스트로 넣지 않는다**(LLM 대신 규칙). 실측 오탐: 09-23 노노카 → 미야코 방송 | `xrelay.is_daily_schedule` + `_maybe_url_confirmed_schedule`. 같은 이유로 이름 언급 게스트 찾기 · LLM 게스트 확인에도 스케줄 인용문을 쓰지 않는다(안 그러면 인용문의 「宮永ののか」로 다시 붙는다). 관리 페이지 미리보기도 같게. 스케줄이 아닌 인용(09-22 리츠 → 유노)은 그대로 |
| D29 | 예고 DM(`_auto_dm` kind 옛 이름 `scheduled` → 어느 레벨에서도 안 나가던 것) **v4a 만** 고친다. 운영 main 은 그대로 | 4곳 kind → `announced` |
| D30 | 같은 멤버의 영상 없는 개인 예고 2건이 하나로 합쳐지는 것 **v4a 만** 고친다 | `preview.match_item` — 채널 페이지 url 은 같은 방송 근거에서 뺀다. 대신 한쪽이 시각 미정이면 JST 같은 날짜끼리 같은 방송(「10/11 配信」 뒤 「10/11 21:00〜」 가 카드 2장이 되지 않게) |
| D31 | 예고를 내리거나 옮기게 한 **휴방 · 변경 글도 원문 보존**(D19 확장) | `_preserve_raw("broadcast_change", …)` — 자동 인입 · 관리 페이지 확정 둘 다, 판정 근거 · 대상과 함께 |
| D32 | v4a 변경의 **운영(main) 반영은 시험 운영 뒤 한꺼번에**. 그사이 운영에 그룹 채널 노래 영상 카드가 생기면 수동 삭제 | — |

## 2. 남은 문제 (미결)

1. **원문 보존(D19) vs 공개 저장소.** 데이터 저장소 `sbb2002/mewtype-scheduler-data` 는 공개 — 인증 없이 raw URL 로
   `tweet_archive.json`(원문 `text`)·`notices.json`(`body_raw`)이 조회됨(2026-09-29 확인). v3.8.0 에서 화면의 원문은
   법률 자문으로 뺐지만 저장소에는 남아 있다. DB 이관 보류(D25)로 원문 보존 위치가 정해지지 않았다.
2. **`search.list` 1회 확인(D4)의 신뢰도.** 비용은 1회 100 units(일 한도 10,000, 현행 light tick 사용량 288/일).
   방송 시작 직후 `eventType=live` 검색 결과에 늦게 잡힐 수 있다는 점, 회원 전용 방송이 검색에 나오는지는 **실측 필요**.
3. **레인 우선 표시(D9)** 구현 전 현행 `render.js` 레인 정렬 확인 필요.

## 3. DB 이관 검토 기록 (D25 보류 근거)

- 프론트는 `preview`·`notices`·`tweets` 3파일을 75초마다 fetch. 1회 약 78KB(gzip 약 18KB) → 방문자 1명·1시간 48회,
  gzip 약 0.86MB / 원본 약 3.7MB (2026-09-29 측정).
- 현행 raw GitHub 는 CDN 캐시(`max-age=300`)가 요청을 흡수하고 전송량이 우리 과금과 무관. Supabase REST 는 공유 캐시가
  없어 **모든 요청이 프로젝트 egress 한도에 합산**(무료 월 5GB로 알고 있음 — 확인 필요).
- 대응안(재개 시): (a) `generated_at` 이 바뀔 때만 본문 조회 (b) 공개 파일은 Supabase Storage 공개 버킷(CDN)
  (c) Vercel 엣지 캐시 경유. 공개/비공개 분리는 RLS(anon 읽기 전용 / 비공개 테이블은 service key).

## 4. 참고 — 검토 중 확인한 현행 사실 (결정과 별개, 정리 후보)

- 종료 DM 의 종료 시각·방송 길이가 항상 "미정": `actual_end` 를 API 에서 받지만(`youtube.py:63`) preview 아이템에
  안 옮김. 시뮬레이션 확인.
- 종료 후 20분 뒤 확인 tick(`handlers._POST_END_RECHECK_SEC`)은 실제로 안 걸림: 트리거가 `"→end"` 로그인데 평소 경로에선
  `preview_build` 가 FSM 전에 end 로 바꿔 `end-check` 로그만 남음. end 창 5분 wake 가 있어 실질 피해 없음.
- 데이터 현황(2026-09-29): 개인 트윗 374건(09-09~09-29) 중 현행 예고 게이트(`parse_schedule`) 재판정 통과 47건 ·
  공식(`@BDP_yumemita`) 소식 62건 · 공식 스케줄 트윗 예고 추가 17건(`monitoring` 로그 09-15~).

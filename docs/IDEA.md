# IDEA — 아직 구현 안 한 아이디어 메모

> 여기 적힌 건 **구상 단계**다. 착수 전에 재검토하고, 구현하면 해당 항목을 `docs/plan/` 로
> 옮기거나 삭제한다. (SPEC/ARCHITECTURE 는 현행 구현만 기술)

---

## 1) 회원전용 방송 감지

**문제**: 회원전용(멤버십) 라이브는 RSS 에 안 잡혀 `/tick` 후보집합에 안 들어간다.
YouTube Data API `videos.list` 는 video_id 만 알면 `liveBroadcastContent: "live"` 를 정상
반환하지만(2026-09-07 유노 `4SJPTPFKPB4` 로 실측 확인), **video_id 를 발견할 경로가 없다.**
현재 우회: 운영자가 `/ingest` 로 URL 이 든 텍스트를 수동 투입 → `scheduled` 행 → 다음 tick 이 승격.

**아이디어**: X(트윗) 릴레이와 같은 방식으로, **5개 유닛의 YouTube 채널에 대해 폰(Automate)에서
알림 설정**을 하고, "○○ さんがライブ配信を開始しました" 류 푸시 알림을 `POST /ingest`(또는 신규
엔드포인트)로 릴레이. 알림 텍스트에서 채널/URL 을 뽑아 후보집합에 주입 → 정규 파이프라인이
`live` 로 확정.

**확인 필요**:
- YouTube 앱이 **회원전용** 방송 시작에도 푸시 알림을 실제로 보내는가? (일반 방송은 보냄.
  회원전용은 안 보낼 가능성 있음 — 미검증)
- 알림 본문에 video_id/URL 이 들어오는가, 아니면 채널명만 오는가 (채널명만이면 그 채널
  `search.list` 1회 = quota 100, 또는 RSS 재시도로 커버)
- 알림 지연·중복·누락 특성 (X 릴레이처럼 dedupe 키 필요)

**관련**: `docs/plan/v2_3_x_relay.md`(릴레이 구조), `docs/AUTOMATE_MANUAL.md`(폰 수식),
`src/backend/xrelay.py`. 회원전용 TTL·`assumed_live` 는 이미 `xrelay`/`reconcile` 에 있음.

---

## 2) 트윗에서 제목·날짜·URL 파싱 — 제목만 LLM 후보

**날짜·URL**: 원문에서 정규식으로 충분히 추출 가능. 현재도 `xnotice._pick_event_date` /
`_site_url_anchor` 가 처리 중. 유지.

**제목**: 현행 `xnotice._headline`(줄별 점수: shout 블록 병합 · 라벨/스트리밍나열 감점 ·
`最終回` 류 가점 · 중간 이모지 제거 등, v2.8.5) 유지. **정규식으로도 역부족인 경우**
(제목이 장식 없는 2~3줄에 개념으로 흩어진 케이스 등)에 한해 **Groq(외부 백엔드2: LLM)** 로
제목만 추출하는 계획.

**설계 방향** (2026-09 논의):
- `xnotice.parse` 는 순수 함수 유지 — LLM 호출은 `telegram_app` 의 impure 레이어에서
  `parse` 성공 후 `merge_notice` 전에 `title`(+`title_slug`)만 덮어씀. 훅 지점: `_apply_notice`
  / `_maybe_auto_notice` 공용 헬퍼.
- `mewtype-telegram` 서비스에서만 돔. `GROQ_API_KEY` → Secret Manager → `deploy_telegram.sh`.
- `requests` 로 OpenAI 호환 엔드포인트(`api.groq.com/openai/v1/chat/completions`), 새 의존성 없음.
  model `llama-3.1-8b-instant`, `response_format=json_object`, 3s 타임아웃.
- 폴백: 키 없음 / 타임아웃 / 429 / 이상응답(길이초과·URL·해시태그 포함·빈값) → 정규식 `_headline`.
- self-test: `GROQ_API_KEY` 있을 때만 도는 통합 테스트 1개 (`gh_store` 의 `GH_TOKEN_TEST` 패턴).
- dedup 무영향: `notices._same_group` 은 `date`+`anchor_a`/`anchor_b` 만 씀 (`title`/`title_slug`
  안 씀).

**미해결**: **환각(hallucination) 대비가 아직 설계에 없음.** LLM 이 원문에 없는 제목을 지어낼 때
거르는 방법 필요 — 예: 출력 제목의 토큰이 원문에 실제로 존재하는지 검사, 또는 confidence 반환
요구 후 임계값 미달 시 폴백.

**착수 조건**: 프로덕션에서 개선된 정규식(`v2.8.5`)으로 2주쯤 돌려보고 "얇은/틀린 제목" 빈도가
여전히 거슬리면. 그전까진 `/notice-edit`(v2.8.3) 수동 교정으로 충분.

---

## 3) 트윗 첨부 이미지를 소식 티커 썸네일로

**배경** (`ref/dm.png` 2026-09-07): 개인 트윗 배지 확인 DM 에 `pic.x.com/XXXX` 만 텍스트로
보냈는데 **텔레그램 서버가 링크를 unfurl** 해서 카드+이미지를 렌더해줬다. 봇이 보낸 게 아니고
unfurl 결과는 클라이언트에만 있어 **봇이 읽어올 수 없다.**

**목표**: 방송 외 홍보 트윗(筋トレ部·Blu-ray·라이브 굿즈 등)의 첨부 이미지를 `notices[].thumbnail`
(계약 H 에 필드 이미 있음)에 넣어 프론트 `notices.js` 티커 카드에 표시. 이미지가 있으면 훨씬 리치.

**이미지 획득 경로 (X API 없이)**:
- **① 신디케이션 엔드포인트** (가장 현실적) — `https://cdn.syndication.twimg.com/tweet-result?id=<트윗id>`
  무인증 JSON, `mediaDetails[].media_url_https` = `pbs.twimg.com/media/...jpg` 직링크. 백엔드는
  이미 `pde_noti_tag` → `_tweet_id` 로 트윗 id 를 가지고 있음 (`pic.x.com` 리졸브 불필요).
  **비공식** — `token`/`features` 파라미터 요구가 수시로 바뀌고 간헐적으로 깨짐·레이트리밋.
  폴백(이미지 없음) 필수. 삭제·연령제한 트윗은 빈 응답.
- **② 폰(Automate) 가 이미지도 릴레이** — 웹푸시 알림에 이미 이미지가 붙어옴 → Automate 가
  multipart 로 `/ingest` 에 텍스트+이미지 동봉. 가장 "무API" 지만 Automate 플로우 수정 필요 +
  웹푸시가 이미지 바이트/URL 을 Automate 에 노출하는지 미검증.
- ③ x.com 페이지 OG 스크랩 → **비추천**. non-browser UA·무로그인 차단, OG 태그 제거됨.

**획득 후**:
- 확인 DM: `sendMessage` → `sendPhoto`(URL) 로 이미지 첨부 (텔레그램 봇 API — X API 아님)
- `notices[].thumbnail` 에 `pbs.twimg.com` URL 저장 → 프론트 카드에 표시
- 프론트에서 `pbs.twimg.com` 핫링크는 대체로 되나 나중에 깨질 수 있음. 소식은 수명 짧아 핫링크로
  감내 가능. 완전하려면 프록시/캐시 필요(저장소 부담).

**판단**: 확인 DM 목적이면 지금도 텔레그램 unfurl 로 충분 → 할 일 없음. 티커에 홍보 이미지를
띄우는 게 목적일 때만 ① 신디케이션. 비공식이라 폴백 필수.

---

## 4) 리트윗은 개인 트윗 파이프라인에서 제외 (버그/하드닝)

**문제**: 멤버가 남의 글을 **리트윗**한 것도 `xtweet.parse` 를 타면 그 멤버의 "개인 트윗
배지"로 사이트에 뜬다. 본인이 쓴 글이 아니므로 배지·예고 승격 모두 대상에서 빼야 한다.

**현행**:
- `xtweet.parse_schedule`(v2.8.1 예고 승격)는 이미 `_HANDLE_HEAD_RE`(`^\s*(?:RT\s+)?@\w{1,15}\s*[:：]`)
  로 `^@user:` 시작이면 `None` → 스킵.
- `xtweet.parse`(v2.8 편지 배지)는 **이 검사가 없음** → 멤버의 RT 가 배지로 저장됨. ← 버그 지점
- `xnotice.parse` 는 `RT @xxx` 를 `src_handle` 에 라벨만 하고 거르진 않음 (소식은 주로
  `@BDP_yumemita` 공식이라 영향 적음. 개인 5인 파이프라인만 우선 대상).

**해야 할 것**:
- 폰 릴레이가 리트윗에 대해 실제로 뭘 보내는지 **특성 파악 필요** (미검증):
  - `android.title` — 멤버 이름인가, 원저자 이름인가? ("○○ 님이 리포스트했습니다" 형태면?)
  - `android.template` — 리포스트 표시가 있나 (BigTextStyle 등)
  - 본문 prefix — `RT @user:` / `@user:` / 신형 리포스트(원저자명 + `@handle` 별도 줄) /
    "리포스트했습니다"·"reposted" 마커
  - 인용 리트윗(코멘트 있음) vs 순수 리트윗 구분
- 파악 후 `xtweet.parse` + `_maybe_personal_tweet` 라우팅에 RT 가드 추가 → `None` 반환
  (배지·예고 둘 다 스킵). `_HANDLE_HEAD_RE` 재사용/확장.
- 보강: `android.title` = 멤버인데 본문 원저자 `@handle` ≠ 그 멤버의 `handle` 이면 RT 로 간주.

**관련**: `src/backend/xtweet.py`(`parse`/`route_by_title`), `telegram_app._maybe_personal_tweet`,
`docs/INGEST_FLOW.md`, `docs/AUTOMATE_MANUAL.md`.

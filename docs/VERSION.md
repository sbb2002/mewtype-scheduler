# VERSION

커밋 메시지의 `feat(vX)` 태그가 실제 릴리스 절차 없이 붙어 히스토리가 흩어져 있어,
버전별 "무엇이 구현됐는지"를 이 파일에서 내림차순으로 관리한다.
(git tag: `v1.0.0`, `v3.0.0`, `v3.0.1`, `v3.0.2`)

- **v3.1.0** — 개인 트윗 스레드 (계약 I 변경): 유닛당 최근 트윗 1건 → **최대 5건**, 메신저 스타일.
  `tweets.json` `tweets[ck]` 가 객체 → **메시지 배열**(최신이 뒤). `xtweet.merge_tweet` → `merge_thread`
  (append·id중복 dedup·`received_at` 정렬·5건 초과분을 오래된 것부터 `tweet_archive.json`(`rolled`)),
  `sweep_expired` 는 메시지별 만료·빈 스레드 키 제거. v2.8 단건 dict 는 `_as_list`/`_tw_list`/`_list`
  shim 으로 하위호환(프론트·백엔드·handlers). 프론트: 배지에 안 읽은 카운트 pill(2건+), 펼치면
  스크롤되는 메시지 스택(PC `.lane__bubble` 패널 / 모바일 `.tw-toast` 시트) — ~2분 내 연속은 시각
  1개로 묶고, 열면 맨 아래로 스크롤 + 표시분 전부 읽음. `한/日` 토글은 전역 1개, 원문 링크는 메시지별.
  **예고 트윗도 본인 글이면 스레드에 실린다**(예고는 preview 승격도 유지 — 이중 노출). RT/타인글만
  `xtweet.parse` 가 제외. 프론트·백엔드 동시 배포 필요(구 프론트가 배열 못 읽음).
- **v3.0.2** — 프론트 UI 정리: (1) 레인 헤더 우측에 세로 이동 레일(`.lane__nav`) 추가 — 이름카드 오른쪽에 YouTube 채널·X 계정 아이콘(X URL = `x.com/<handle>` 재사용, 별도 X 핸들 필드 없음). 아바타 전체가 트윗 말풍선 토글, 이름 글자·레일 아이콘은 채널 이동으로 역할 분리(편지 뱃지 19px 만 조준해야 하던 문제 해소). 헤더 `display:flex` 3열(`tweets.css` 가 `layout.css` override). SVG 아이콘은 `render.js svgIcon()`(`createElementNS`). (2) PC 예고 버킷도 모바일과 동일하게 3분할(`오늘`/`7일 이내`/`7일 이후`) — `한 달 이내`+`그 이후` 통합, `bucketKey` 의 `_mobileMQ` 분기 제거. 백엔드 배포 불필요(Vercel 정적)
- **v3.0.1** — 개인 트윗 핫픽스 3건: (1) 번역 토글 버튼 `onclick` 을 매 렌더 재바인딩 — 다른 유닛 트윗을 열면 첫 유닛 본문으로 오염되던 것 차단. (2) `_expand_truncated_yt` — 웹푸시로 `…` 잘린 YouTube URL 을 `vxtwitter` unfurl 로 복원(만들어두고 미연결이던 모듈 연결), `video_id` 시드 실패로 `announced` 가 FSM 추정 승격되던 것 방지. (3) `_inline_translate` — 자동 인입 트윗을 merge 직후 인라인 번역(실패 시 `needs_tl` 큐잉) — 자동 경로에 번역 호출도 `needs_tl` 세팅도 없어 편지 배지 번역 토글이 영영 안 뜨던 것 수정. `mewtype-telegram` 재배포
- **v3.0.0** — 백엔드 수술 (배포 2026-09-09): `schedule.json`→`preview.json`(계약 A′), 3상태→6상태(`none|announced|upcoming|watching|live|end`), `pending.json` 폐지(FSM 을 `preview` 아이템에서 파생, `statemachine.py` 재작성). 새 모듈 `preview.py`/`preview_build.py`/`llm.py`(Groq `gpt-oss-120b` 번역·소식 제목추출)/`ytnotif.py`/`vxtwitter.py`. 소스 신뢰도 티어 머지 모델(1 API / 2 명시값 / 3 파생값). 텔레그램 `{cmd}×{contents}` 격자(`/list /ingest /edit /del /undo /translate × preview|notice|tweet`). 데이터 콜드 스타트(v2 파일 `data:.old/`)
- **v2.8.5** — 소식 파서 정밀화: (1) `_DATE_RE` 명시 연도(`2025年9月7日`) 캡처 + `_RE_RETRO`(`今日は何の日`·`N年前`) → `is_recap`, `merge_notice` 는 지난 날짜 신규 소식을 무조건 skip (회고글이 오늘 이벤트로 잘못 등록되던 것 차단). (2) `_headline` — `_TITLE_NOUN_RE`(`最終回` 등) +25 · `_STREAM_LIST_RE`(`ABEMA/Prime Video/…` 나열) −35 · 날짜시작 −15 이벤트명사 면제 · 역방향 `／…＼` 병합 · `_MID_DECO_RE` 중간 장식 이모지 제거 · `_RE_LIVE` 에 `最終回`/`最終話`
- **v2.8.4** — `LIVEWATCH_EARLY_SEC` 30분 → 10분: 라이브 시작 후 첫 60분 폴링 간격을 좁혀 55~90분짜리 단시간 방송의 종료 감지 사각(체크 사이 공백에 방송이 끝나 최대 ~30분 지연)을 축소. 60분 이후는 그대로 3분(`LIVEWATCH_TIGHT_SEC`)
- **v2.8.3** — (1) 수동 `/ingest` 개인 예고 폴백: `@BDP` 형식이 아니면 `_try_personal_ingest` 가 본문 YouTube URL → `videos.list`(quota 1)로 5인 채널 판별 → `xtweet.parse_schedule`+`merge_personal_schedule`. URL 없음/판별 실패면 `pending_member` 슬롯 + `[1~5]` 유닛 되묻기(`_handle_member_followup`). `mewtype-telegram` 에 `YOUTUBE_API_KEY` Secret 추가. (2) `/notice-edit <id|번호>` — 제목→날짜→URL 순 되묻기 마법사(`pending_notice_edit` 슬롯, 유지=`aNoneTokyo`), `notices.edit_notice` 로 커밋(파생값 재계산·`/undo`). (3) `xnotice._headline` 개선 — `_join_shout_titles`(`💪…💪` 여러 줄 제목 병합) + `_LABEL_LINE_RE`(`日程：`/`会場：` 라벨 줄 감점)
- **v2.8.2** — DM 로그 레벨 재정의: `notify.allows` 를 kind(scheduled/upcoming/live/notice/tweet/ingest) 기준으로 개편. `simple`=upcoming·live만 / `normal`=+scheduled·notice·tweet / `detail`=+ingest·fallback·요약. 자동 DM(소식·트윗·본인예고·ingest 결과)에 `_auto_dm` 게이팅 적용(운영자 명령 응답은 제외)
- **v2.8.1** — 개인 트윗 예고 → `scheduled` 승격: `xtweet.parse_schedule`(`配信`+날짜[+시각]/URL 게이트) → `merge_personal_schedule`(같은 방송 upsert·붕괴), `time_tbd`(날짜만) 지원. `handlers.apply_overrides` 후처리로 최신 트윗 시각이 API 재구성을 override(`api_start_seen` 로 스트림 실수정 시만 API 승). 계약 A 에 `source`/`time_tbd`/`info_source`/`info_at`/`api_start_seen` 추가
- **v2.8** — 멤버 5인 개인 트윗: `POST /ingest` 가 `android.title` 로 라우팅 → 개인 트윗은 `tweets.json` 파이프라인(24h 수명·최신 교체·`tweet_archive.json` 로깅), 예고판 상단 유닛 아바타에 파란 편지 배지(PC 호버·고정 말풍선 / 모바일 토스트, 퍼스널 컬러 배경). 테스트 부계정(`jehy`)은 강제 ECHO 헬스체크
- **v2.7.1** — 소식 티커 마감: 0건도 빈 막대 유지, 펼침을 예고판 위 오버레이(밖 탭 닫힘·슬라이드)로, 모바일 버킷 통합·레이아웃 침범 수정
- **v2.7** — 방송 외 이벤트(라이브 예고·음반/굿즈·타 플랫폼·기타) 자동 수집·중복제거·수명관리 + 예고판 상단 소식 티커
- **v2.6.1** — `/ingest` 가 X 알림의 게시자 이름·template·트윗 태그도 수신, 트윗 링크 도출 (소식 게시판 준비 단계)
- **v2.6** — 합동방송이 참여 멤버 개인 채널에서 열려도 트윗 URL(video_id)로 실물 확정·전원 레인 팬아웃, bilibili·全員 라인 스킵
- **v2.5.2** — `/undo` 를 y/N 되묻기 2단계로 전환, 되돌릴 시점(KST·커밋)과 복원/제거 broadcasts 목록을 먼저 표시
- **v2.5.1** — `/ingest` 를 2단계 대기(텍스트/파일 첨부, `aNoneTokyo` 취소)로 전환, DM 에 인식 실패 줄 수 표기
- **v2.5** — 텔레그램 수동 관리 명령 `/list` `/del` `/ingest` `/undo` (admin_state.json 슬롯 + SHA 가드 undo)
- **v2.4** — 합동방송 카드를 참여 멤버 전원 레인에 팬아웃, `出演情報`(외부 이벤트 출연) 트윗 파서 추가
- **v2.3** — `@BDP_yumemita` 일일 스케줄 트윗을 폰이 릴레이 → YouTube 영상 없는 `scheduled` 예고 행으로 반영
- **v2.1** — Telegram 봇 상태 모니터링·원격 제어(`/status` `/pause` `/resume` `/log`) + 상태 전이 DM 알림
- **v2.0** — Cloud Run 스케일-투-제로 백엔드 — Cloud Scheduler + Cloud Tasks 방송별 wake + pending.json 폴링 FSM
- **v1.2** — '오늘'(24h 이내) 구간 + 분 단위 카운트다운 + 예정 방송 지각(n분/시간) 표시
- **v1.1** — 모바일 1인 1화면 무한 캐러셀 + 레인 헤더·버킷 피드 영역 재디자인
- **v1.0** — 5채널 RSS+YouTube API 수집 → 시간순 방송 예고판, 반응형 정적 사이트 (Vercel + GitHub Actions)

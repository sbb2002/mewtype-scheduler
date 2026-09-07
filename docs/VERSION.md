# VERSION

커밋 메시지의 `feat(vX)` 태그가 실제 릴리스 절차 없이 붙어 히스토리가 흩어져 있어,
버전별 "무엇이 구현됐는지"를 이 파일에서 내림차순으로 관리한다. (git tag 는 `v1.0.0` 하나뿐)

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

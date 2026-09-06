# VERSION

커밋 메시지의 `feat(vX)` 태그가 실제 릴리스 절차 없이 붙어 히스토리가 흩어져 있어,
버전별 "무엇이 구현됐는지"를 이 파일에서 내림차순으로 관리한다. (git tag 는 `v1.0.0` 하나뿐)

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

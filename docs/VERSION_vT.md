# 테스트판 버전 기록

<!-- ENTRIES: 최신이 위 -->

## vT1.0.1 — 2026-10-27 11:57 KST · 핫픽스 (자동)

- **제목**: fix: gh_store 1MB 넘는 파일을 Git Blob API 로 읽어 개인 트윗 반영 실패 해결
- **에러**: `telegram_app-1330ba5e` — tweet_archive.json이 1MB를 넘어 Contents API가 content를 비워 개인 트윗 반영 실패
- **변경**: `docs/SPEC.md` (+1 −0), `src/backend/gh_store.py` (+155 −42) · 합계 +156 −42
- **커밋**: `9c8c778` → `1449072` · 브랜치 `auto/telegram_app-1330ba5e-1` · 파이프라인 표준(충분한 검증)


## vT1.0.0 — 기준선

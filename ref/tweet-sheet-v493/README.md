# 트윗 시트 v4.9.3 (2026-10-28) — 자료

일반 패치 v4.9.3(브랜치 `hotfix/tweet-sheet-media`)의 설계 자료. 정본은 `main` 의 `docs/SPEC.md` 「트윗 시트」 절이다.

- `spec.html` — 구현 명세(운영자와 주고받으며 고친 마지막 판). 확정 결정 · X 카드 실측 · 파일별 할 일 · 확인 방법.
- `prototype.html` — 구현 뒤 모습을 미리 만져 본 시제품(예시 데이터 · X 카드 흉내). 마지막 판 = 사진은 보기만, 영상 칸만 원문 카드로 + 글로우.
- `serve_local.py` — 로컬 확인 서버(`/` = 워크트리 `src/frontend`, `/data/` = 내려받은 data 사본).
  `python -X utf8 -I serve_local.py <워크트리>/src/frontend <data 사본 폴더> 8766` → `http://127.0.0.1:8766/index.html`
- `make_test_tweets.py` — data 사본 `tweets.json` 의 유노 글타래에 실제 X 글 7개(영상 · 섞인 미디어 · 인용 · 자기 답글)를 시험 글로 덧붙인다(fxtwitter 로 받음). 운영 데이터는 건드리지 않는다.

## X 카드 실측 (10-28, `platform.twitter.com/embed/Tweet.html`, 카드 폭 345 · 405 · 505 · 550px 에서 같음)

테두리 1 · 안쪽 위 12 / 옆 16 · 머리 줄 48 · 12 뒤 (답글이면 「@핸들 님에게 보내는 답글」 24 뒤) 본문 20px/24px ·
12 뒤 미디어(2~4칸 = 16:9 묶음, 1칸 = 원래 비율 · 세로는 정사각형, 칸 사이 2 · 테두리 1 · 모서리 12) ·
12 뒤 인용 상자(테두리 1 · 여백 12 · 이름 줄 26 · 본문 15px/20px · 12 뒤 미디어를 아래에 붙임) ·
8 뒤 시각 줄 20 · 그 아래 100(7개 글 모두 같음). 글꼴 = 시스템 글꼴(-apple-system, Segoe UI, Roboto …), 화면 폭과 무관하게 20px.
측정 방법: `platform.twitter.com` 탭에서 같은 출처 iframe(폭 지정, `scrolling="no"`)으로 열어 `contentDocument` 의 위치를 잰다.

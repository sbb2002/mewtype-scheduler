# 달 궤도 지구돋이 3자 비교 (2026-11-09)

Claude · Codex · agy 가 같은 의뢰서(`moon_brief.md` · `moon_impl.md`)로 각자 따로 구현. 코드 = 브랜치 `test/bg-moon-claude` · `test/bg-moon-codex` · `test/bg-moon-agy`(feat/bg-dome `1ae7073` 에서 갈라짐, 병합 안 함).
- `shots/` 대신 이 폴더에 `<이름>_alt15 · alt38 · alt60`(claude 는 15 · 38 만), codex 는 `_horizon` · `_zoom30` · `_canvas` 추가.
- `moon_<이름>_report.md` = 각 안의 설명 · 한계. `moon_codex.md` · `moon_agy.md` = 구현 전 설계 자문.
- 시각 평가: agy 가 가장 자연스러움(알베도 변화 · 다단계 크레이터 · 곡면 지평선 · 대기 번짐), Codex = 어둡고 절제(줌 ×30 노출 보정 있음), Claude = 선명하나 모형 같음. 폰 실측 · GPU 비용 비교는 아직.

## 폴더
공통 = `moon_brief.md`(의뢰 배경) · `moon_impl.md`(구현 지시). 모델별 폴더 `claude/` · `codex/` · `agy/` 에 각자 만든 것 —
`alt15 · alt38 · alt60.*`(캡처) · `report.md`(설명 · 한계) · `design.md`(구현 전 설계 자문, claude 는 없음) · `code.patch`(feat/bg-dome `1ae7073` 대비 src 변경, `git apply` 가능).

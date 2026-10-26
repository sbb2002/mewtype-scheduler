# 사람 조치 필요 — 실전 시험 결과 (2026-10-13)

대상: 외부 API 의 인증 · 결제 · 쿼터 · 계정 문제를 자동 패치가 어떻게 다루는가 (`docs/AUTOFIX.md` §11).
방법: `python -m src.busrx.live_human_check` — **진짜 claude**(분석 · 명세 Sonnet 5.5, 구현 Haiku 5.5)로 시나리오별 에러 봉투 1건씩을 처리.
저장소는 임시 폴더로 복제해 그 안에서만 수정 · 커밋했고(재시작 없음), 실제 저장소 · 러너 · 수신기에는 손대지 않았다(실제 저장소의 `fault_lab.py` 변경 없음 확인).
정책: ERROR · WARN 모두 자동 수정(`fix`), 모드 자동, 수신기 2단계.

## 결과

| 시나리오 | 에러 내용(요약) | 기대 | 판정 | needs_human | 수정 단계 시작 | 표시 | 텔레그램 알림 | 소요 |
|---|---|---|---|---|---|---|---|---|
| groq401 | Groq 401 Invalid API Key | 사람 | confirmed | **true** | 아니오 | 예 | 예 | 20초 |
| groq402 | Groq 402 Payment required (무료 티어 종료) | 사람 | confirmed | **true** | 아니오 | 예 | 예 | 18초 |
| yt403 | YouTube videos.list 403 quotaExceeded | 사람 | confirmed | **true** | 아니오 | 예 | 예 | 33초 |
| github401 | GitHub PUT 401 Bad credentials(토큰 만료) | 사람 | confirmed | **true** | 아니오 | 예 | 예 | 25초 |
| telegram401 | Telegram sendMessage 401(봇 토큰 폐기) | 사람 | confirmed | **true** | 아니오 | 예 | 예 | 23초 |
| codebug (대조) | `fault_lab.clamp` 반환값 뒤바뀜(코드 결함) | 수정 | confirmed | false | **예 → 적용(applied)**, `src/backend/fault_lab.py` | 아니오 | 아니오 | 71초 |
| transient503 (대조) | Groq 503 백오프 소진 단발 WARN | 아무 조치 없음 | unknown | false | 아니오 | 아니오 | 아니오 | 22초 |

- 외부 서비스 5종(LLM 2건 · YouTube · GitHub · 텔레그램)이 **전부** 사람 조치 필요로 판정됐고 수정 · 계획안 단계가 시작되지 않았다.
  분석기가 쓴 「사람이 할 일」은 구체적이었다(예: Groq 402 → "결제 수단을 등록해 유료로 전환할지, 다른 LLM 공급자로 교체할지 결정", YouTube 403 → "쿼터 증설 신청 ·
  키 교체/분리 · 호출 빈도 축소 중 결정, 쿼터는 태평양시 자정에 초기화", 텔레그램 401 → "BotFather 에서 토큰 재발급, 어느 봇인지 확인, 유출 여부 점검").
- 코드 결함(대조군)은 정상적으로 수정 파이프라인을 끝까지 탔다 — 사람 조치 필요 판정이 수정 기능을 막지 않는다.
- 단발 일시 장애는 사람 조치도 수정도 아닌 `unknown`(분석기가 스냅샷에서 해당 로그 문구를 못 찾아 확정 불가라고 정직하게 답함)으로 끝났다.

## 한계 · 확인 안 된 것

- 시나리오당 **1회 실행**이다(분석기 판정은 모델 출력이라 매번 같지 않을 수 있다). 안정성은 운영하며 지켜봐야 한다.
- 에러 메시지는 실제 공급자 응답을 흉내 낸 합성 입력이다. 실제 장애 때 메시지 형태가 다르면(예: 한 줄에 상태 코드가 없는 SDK 예외) `needs_human` 판정이 달라질 수 있다.
- 분석기가 `needs_human=false` 로 잘못 판정하고 명세서도 `fixable=true` 로 가는 경우의 마지막 방어선은 가드의 「새 외부 호스트 · 환경변수 이름 금지」다 —
  이 경로는 가짜 claude 로 `selftest_fix` S3b 에서 시험했고(폐기됨), 진짜 claude 가 공급자 교체 패치를 만들어 오는 상황은 이번에 유도되지 않았다.
- 반자동 모드에서의 진짜 claude 시험은 하지 않았다(가짜 claude 로 계획안이 만들어지지 않음을 `selftest_human` 에서 확인).

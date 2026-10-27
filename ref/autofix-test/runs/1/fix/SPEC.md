# 개인 트윗 아카이브 읽기 실패 시 폴백·대용량 raw 읽기 추가

## 변경 계획
- `src/backend/gh_store.py`: read_json(113~127행 부근): 200 응답인데 content 가 비어 있으면 곧바로 RuntimeError 를 던지지 말고, 같은 contents URL 에 헤더 `Accept: application/vnd.github.raw` 를 붙여 한 번 더 GET 하여 본문을 그대로 json.loads 한다(sha 는 첫 응답의 sha 사용). 새 호스트·환경변수는 추가하지 않는다. raw 재조회도 실패하거나 본문이 비면 기존 메시지(`No content in response for {path}`)로 RuntimeError 유지. 한국어 주석으로 「1MB 초과 파일은 content 가 비어 올 수 있음(추정, 코드로 증명되지 않음)」을 명시. write_json 은 내부에서 read_json 을 쓰므로 같은 경로 혜택을 받는지만 확인하고 그 외 변경 없음.
- `src/backend/telegram_app.py`: _commit_personal_tweet(2160~2192행): 아카이브 읽기를 별도 try/except 로 감싼다. 실패하면 log.warning 을 남기고 arch=xtweet.default_archive(), asha=None, arch_ok=False 로 두어 tweets.json 반영은 계속한다. 아카이브 쓰기 조건을 `if arch_ok and new_a is not arch:` 로 바꿔, 읽지 못한 기존 아카이브를 기본값으로 덮어쓰지 않게 한다. 정상 읽기 경로(arch_ok=True)의 동작은 기존과 동일. tweets.json 읽기 실패는 기존대로 바깥 except 로 전파.

## 테스트 계획
1) gh_store: requests 세션을 가짜로 주입해 (a) 첫 응답 200+content "" → 두 번째(raw 헤더) 응답이 JSON 본문일 때 (data, sha) 반환, (b) 두 번 다 빈 본문이면 RuntimeError, (c) 404 는 (None, None) 유지하는지 확인(`python -m src.backend.gh_store` self-test 에 케이스 추가 가능하면 추가). 2) telegram_app: gh 목(mock)으로 tweets.json 은 정상, tweet_archive.json read_json 이 RuntimeError 를 던지게 하여 _commit_personal_tweet 이 mode 가 error 가 아니고 tweets.json 쓰기는 1회 일어나며 아카이브 write_json 은 호출되지 않는지 확인. 정상 읽기 시 아카이브 쓰기가 기존처럼 일어나는지도 확인. 3) `PYTHONIOENCODING=utf-8 python -m src.backend.telegram_app` 및 `python -m src.backend.xtweet` self-test 통과. 운영 자원은 건드리지 않고 로컬 목으로만 검증.

## 위험
content 가 비는 실제 원인(1MB 초과)은 코드로 증명되지 않았고 로그의 env 가 local 시험이라 가정에 의존한다. raw 재조회가 통하지 않는 경우 증상은 그대로이나, 폴백 덕에 tweets.json 반영은 유지된다. 아카이브 읽기 실패 시 이번 트윗의 아카이브 이동분은 기록되지 않아 일시적으로 누락될 수 있다(기존 아카이브 보호가 우선). 아카이브 회전·분할은 계약(SPEC) 변경이 필요하고 docs/ 수정이 금지돼 이번 범위에서 제외한다.

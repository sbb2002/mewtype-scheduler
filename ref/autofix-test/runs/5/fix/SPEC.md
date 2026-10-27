# 1MB 초과 파일을 읽지 못하는 gh_store 읽기 폴백 추가

## 변경 계획
- `src/backend/gh_store.py`: GitHubStore 에 내부 메서드 `_get_raw(path)` 를 추가한다. 같은 URL·params 로 GET 하되 헤더 Accept 만 `application/vnd.github.raw+json` 으로 바꾸고, 200 이면 resp.text(UTF-8 로 디코딩한 본문)를 돌려주고 그 외 상태코드는 기존 read 와 같은 형식의 RuntimeError 를 던진다. 새 호스트·환경변수는 없다.
- `src/backend/gh_store.py`: read_json: `content` 가 비어 있고 `encoding == 'none'` 이면(Contents API 가 1MB 초과 파일에 주는 응답) RuntimeError 를 던지는 대신 `_get_raw` 로 본문을 받아 json.loads 한다. sha 는 1차 응답의 `sha` 를 그대로 쓴다. encoding 이 'none' 이 아닌데 content 가 빈 경우(예: 빈 파일 등 다른 원인)는 기존처럼 RuntimeError 를 유지해 원인을 가리지 않는다. write_json 이 read_json 을 호출하므로 같은 폴백이 쓰기 경로(비교·sha 조회)에도 적용된다.
- `src/backend/gh_store.py`: read_text 도 같은 폴백을 적용한다(동일한 `encoding == 'none'` 분기 → `_get_raw`).
- `src/backend/gh_store.py`: `if __name__ == '__main__':` self-test 에 회귀 검사를 추가한다. _FakeSess.get 이 Accept 헤더가 raw 이면 본문 텍스트를, 아니면 `{content:'', encoding:'none', size:1138183, sha:'shaBig'}` 를 돌려주는 가짜 세션으로 (a) read_json 이 (데이터, 'shaBig') 를 돌려주고 raw 요청이 1회 나가는지, (b) read_text 도 동일한지, (c) write_json 이 큰 파일에 대해 내용 동일하면 PUT 없이 (False,'shaBig'), 다르면 sha='shaBig' 로 PUT 하는지, (d) encoding 이 'none' 이 아닌 빈 content 는 여전히 RuntimeError 인지 검증한다.

## 테스트 계획
`PYTHONIOENCODING=utf-8 python -m src.backend.gh_store` 로 추가한 self-test(가짜 세션, 네트워크 불필요)를 돌려 기존 검증 1~6 과 새 검증이 모두 통과하는지 확인한다. 이어서 `python -m src.backend.telegram_app` self-test 가 깨지지 않는지 확인한다. 운영 저장소는 건드리지 않는다.

## 위험
raw 미디어 타입 폴백은 GitHub 문서상 1MB 초과 파일(최대 100MB)에 쓸 수 있다고 알려져 있으나, 이 환경에서 실제 호출로 확인하지는 못했다(확인 필요). 같은 파일에 대한 PUT 이 1MB 초과에서도 되는지도 실측하지 못했다 — 문서상 PUT 한도는 100MB 이다. 아카이브가 커질수록 읽기·쓰기당 전송량과 Cloud Run 처리 시간이 늘어나므로, 크기 관리 정책은 별도 결정이 필요하다. 폴백만으로 원인(읽기 불가)은 해소되지만 파일 증가 자체는 막지 못한다.

## 자동 결정한 값
- 아카이브 보존 기간·건수 상한은 이번에 넣지 않는다 — tweet_archive 는 기록용이라 자르면 데이터 삭제(땜질 금지)가 되고, 트윗 수명(48h)은 표시용이지 아카이브 보존 정책이 아니라는 근거가 코드에 없다. 읽기 한계 자체를 고치는 쪽이 원인 수정이다.
- 폴백 조건 — `encoding == 'none'` 일 때만 raw 재요청, 근거: 분석 로그의 실제 응답이 encoding='none', size=1138183 이었고 다른 빈 content 는 원인을 숨기지 않기 위해 계속 오류로 둔다.
- 데이터 이전 스크립트 불필요 — 저장 형식·경로가 바뀌지 않는다.

## ⚠️ 민감 경로 수정
- `src/backend/gh_store.py`
- `src/backend/gh_store.py`
- `src/backend/gh_store.py`
- `src/backend/gh_store.py`

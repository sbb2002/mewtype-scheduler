# contents

- 메인컨텐츠인 preview, notice, tweet을 의미.
- preview : 방송 예고 보드
- notice : 상단의 공식 이벤트 게시판
- tweet : 개인 유닛의 최근 트윗 뱃지


# 일반 명령

`/log` `/pause` `/resume` 는 현행과 동일. `/status` 는 v3 골격(preview/notice/tweet 3계통 +
상태 6종 + LLM 큐)에 맞춰 재구성.

## `/status`

출력 양식:
```
🟢 mewtype v3  |  paused: no  |  log: normal

preview  announced 3 · upcoming 1 · watching 0 · live 1 · end 0
notice   4건 (가장 이른 D-2)
tweet    arale, nonoka, yuno  (3/5)

동기화
  마지막 tick     2026-09-09 21:03 JST  (ok)
  마지막 커밋     2026-09-09 21:03 JST  → data 브랜치
  다음 baseline   2026-09-10 06:00 JST
  다음 light      2026-09-10 00:00 JST
  다음 정밀 체크  2026-09-09 21:12 JST  (live 1건)

LLM 큐    0건 대기
업스트림  마지막 수신 21:01 JST · 헬스체크(jehy) 20:55 JST
```

- `paused: yes` 면 첫 줄 아이콘을 🔴 로.
- `preview` 카운트는 **살아있는 아이템(announced~end)만**. archive 제외.
- `다음 정밀 체크` = watching/live 아이템의 다음 wake 예정 중 가장 이른 것. 없으면 이 줄 생략.
- `LLM 큐` = 외부 LLM 작업 큐 대기 건수. 미도입 상태면 `-`.
- `업스트림` = 마지막 `/ingest` 수신 시각 + 헬스체크(테스트 부계정) 마지막 수신 시각.


# 메인 컨텐츠 명령어

## 공통 규칙

- **취소 토큰**: 모든 되묻기 단계에서 `aNoneTokyo` 입력 = 이 명령 전체 취소.

- **단계별 60초 타임아웃**: `/edit` · `/del` 의 각 문답은 60초 내 응답이 없으면 자동취소.
  (편집 후 충돌 알림의 되묻기, `/del` 최종확인도 동일 — 아래 각 절 참조.)

- **idx 안정성**: `/list` 결과의 idx 는 그 명령이 방금 출력한 스냅샷 전용 표시번호다.
  실제 처리 대상은 `preview.json` 의 `id`(`pv_xxxx`) 로 잡는다. 운영자가 idx 를 답한 시점에
  그 스냅샷 idx 가 가리키던 `id` 가 아직 살아있으면 처리, 사라졌으면 "이미 없어진 항목" 안내 후 중단.

- **아이템 단위 편집 락** (전체 `/pause` 안 씀): `/edit` · `/del` 세션이 대상 `id` 를 확정하면
  `admin_state.edit_lock = {id, until}` 를 건다. `until` = 마지막 문답 시각 + 60초, 세션 종료 시 해제.
    - `/tick` · `/wake` 는 평소대로 RSS·API·알림·다른 아이템 커밋을 다 한다. **락 걸린 그 `id` 의
      `preview.json` 쓰기만 이번 사이클에서 건너뛴다.** 다른 콘텐츠(notice/tweet)도 영향 없음.
    - 백엔드는 안 멈추므로 `/wake` 로 인한 live/end 추적 지연이 없다.

- **답한 필드만 patch**: `/edit` 커밋은 운영자가 실제로 답한 필드만 대상 행에 병합하고
  나머지 필드는 현재 파일값을 유지한다(v2 `edit_notice(prev,nid,patch,now)` 방식). 락 기간에
  tick 이 다른 필드를 갱신했어도 덮이지 않는다.

- **편집 후 충돌 알림**: 락 해제 시, 그 사이 tick 이 같은 `id` 의 **운영자가 답한 필드와 겹치는
  필드**를 바꿨으면 알림 1개: `필드: [운영자값] ↔ [tick값]  유지 / 재편집?`
    - 60초 무응답 → 운영자값 유지(방금 명시적으로 넣은 값이므로).
    - 겹치는 필드가 없으면 알림 없음(patch 로 이미 무충돌).

## `/list [contents]`
- if contents=='preview', 5인 멤버 전체의 **살아있는 방송예고 아이템(상태 announced~end 전부)** 을
  보여줌. archive(none 으로 소멸한 것)는 제외. `[상태]` 는 `preview.json` 의 `state`
  (`announced`/`upcoming`/`watching`/`live`/`end`) 를 그대로 표기 — `live` 는 `live(n분)`,
  `end` 는 `end(종료)` 로. 양식은 아래와 같음.
    ```
    [#퍼스널컬러 동그라미 이모지] [유닛이름(변수명); eg. 나카마치 아라레(arale)]
    
    [idx; 개인별로 인덱싱할것] [제목]
    [상태] [날짜/시각] 
    [url]

    [idx; 개인별로 인덱싱할것] [제목]
    [상태] [날짜/시각] 
    [url]

    ---

    [#퍼스널컬러 동그라미 이모지] [유닛이름(변수명); eg. 나카마치 아라레(arale)]
    
    [idx; 개인별로 인덱싱할것] [제목]
    [상태] [날짜/시각] 
    [url]

    ...

    ```

- if contents=='notice', 현재 게재된 게시판의 모든 정보를 보여줌. 양식은 아래와 같음.
    ```
    [보드 이모지] 소식 정보

    [idx] [제목]
    [소식종류] [날짜/시각] [D-day]
    [url]

    ...
    ```

- if contents=='tweet', 현재 게재된 최근 트윗을 표시. 양식은 아래와 같음.
    ```
    [#퍼스널컬러 동그라미 이모지] [유닛이름(변수명); eg. 나카마치 아라레(arale)]
    [내용]
    [게시 날짜/시각]
    [url]

    ```


## `/ingest [contents]`

- if contents=='preview', 먼저 어떤 유닛을 대상으로 ingest하는지 되묻기(2명 이상인 경우 합동으로 간주; eg. arale, nonoka) -> 원문 요청하기 -> 원문으로부터 날짜/시각, 제목, url 등을 파싱하여 ingest 수행.(사용자가 누구에게 넣을지 명시했으므로 url을 활용한 유닛 자동 감지는 하지 않도록 한다.)
    - **합동 시 주 레인**: 입력 순서 첫 번째가 `channel_key`(주 레인), 나머지가 `collab_with`.
      운영자는 방송을 실제로 여는 채널을 먼저 쓴다. (`channel_key` 는 url 확정 전 상태머신의
      기준 채널이자 아이템 매칭·supersede 앵커. 프론트는 union 레인 팬아웃이라 표시는 무관.)

- if contents=='notice', 원문 요청하기 -> notice에 대한 ingest 수행.

- if contents=='tweet', 어떤 유닛을 대상으로 할지 묻기 -> 원문 요청하기 -> tweet에 대한 ingest 수행.


## `/edit [contents]`

- 공통 : [contents]에 해당하는 `/list`를 실행하여 가장 먼저 정보 제시.

- if contents=='preview', 어떤 유닛을 대상으로 할지 묻기 -> idx 묻기 -> 'edit form #1'을 제시하며 어떤 것을 수정할지 묻기 또는 ingest 모드로 진입할지 묻기 -> (1) 사용자가 title, level 등 선택 / (2) 사용자가 ingest라고 답변 -> (1) 언급한 순서대로 한번에 하나씩 원문 요청하기 / (2) ingest와 같이 원문을 요청하기 -> 수정 반영
    ```edit form #1
    [유닛 이름] [idx]
    * title : [제목]
    * state : [상태]
    * date : [날짜/시각]
    * URL : [url]
    ```
    - `state` 를 수동으로 바꾸면 다음 tick 의 FSM 파생이 덮을 수 있음(상태는 원래 파생값).
      강제 교정용이며, url 을 살린 채 announced 로 되돌리는 정도가 실용 범위.

- if contents=='notice', idx 묻기 -> 'edit form #2'를 제시하며 어떤 것을 수정할지 묻기 또는 ingest 모드로 진입할지 묻기 -> (1) 사용자가 title, level 등 선택 / (2) 사용자가 ingest라고 답변 -> (1) 언급한 순서대로 한번에 하나씩 원문 요청하기 / (2) ingest와 같이 원문을 요청하기 -> 수정 반영
    ```edit form #2
    소식 정보 [idx]
    * title : [제목]
    * category : [소식종류]
    * date : [날짜/시각] [D-day]
    * URL : [url]
    ```

- if contents=='tweet', 어떤 유닛을 대상으로 할지 묻기 -> 수정할 원문 요청하기 -> 수정 반영


## `/del [contents]`

- 공통 : [contents]에 해당하는 `/list`를 실행하여 가장 먼저 정보 제시.

- if contents=='preview', 먼저 어떤 유닛을 대상으로 delete하는지 되묻기 -> idx 요청하기 -> 최종확인
- if contents=='notice', idx 요청하기 -> 최종확인
- if contents=='tweet', 어떤 유닛을 대상으로 할지 묻기 -> 해당 유닛의 현재 트윗 존재 여부 확인 -> 최종확인

### 최종확인 — `(terminate/y/N)`

- **`y`** : 그 아이템만 삭제하고 끝. (다음 tick 이 원본을 다시 감지하면 재등록될 수 있음.)
- **`N`** (기본, 60초 무응답 포함) : 취소.
- **`terminate`** (preview 한정) : 삭제 + 그 `url` 을 **12시간 재진입 차단**.
    - `admin_state.suppress = [{url, until}]` 에 `until = now + 12h` 로 등록.
    - `/tick` reconcile 이 후보 url 을 이 목록과 대조해 매치되면 아이템을 만들지 않는다.
      `until` 지나면 목록에서 제거(다음 sweep). `/ingest` 수동 입력도 같은 검사 — 차단 중이면 거부.
    - `url` 이 없는 `announced` 행에 `terminate` 하면 차단할 키가 없으므로 `y` 와 동일하게 처리하고
      그 사실을 알림.


## `/undo`

- 되돌림 대상 = **직전에 운영자가 이 제어 채널에서 실행한 mutating 명령 1건**
  (`/ingest` `/edit` `/del` 중 마지막). tick/wake 등 백엔드 자동 동작은 대상 아님.
- 계통(preview/notice/tweet) 무관 단일 슬롯. 슬롯은 다음 mutating 명령이 성공하면 덮인다.
- 방금 작업 내역을 제시한 후 정말로 되돌린다고 한번 더 되묻기.


## `/translate [contents]`

- 공통 : [contents]에 해당하는 `/list`를 실행하여 가장 먼저 정보 제시.
- if contents=='preview', 어떤 유닛을 대상으로 하는지 묻기(all이라고 답하면 전체 유닛와 idx 해당) -> idx 묻기(all이라고 답하면 이 유닛의 idx 전체 해당) -> 해당 예고의 제목에 대해 번역 수행.
- if contents=='notice', idx 묻기(all이라고 답하면 전체 해당) -> 소식 제목에 대해 번역 수행.
- if contents=='tweet', 어떤 유닛을 대상으로 하는지 묻기(all이라고 하면 전체 유닛 해당) -> 현재 트윗 내용에 대해 번역 수행.
- 번역해도 원문은 보존해야함. json에 저장할 때 반드시 원문을 함께 저장하도록 함. 왜냐하면 tweet의 경우 토글식으로 원문<->번역 가능하게 하기 위함.


# 기타
- 그 외 명령어는 현재와 동일.
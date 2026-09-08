# 현재 버전(v2)의 앱 상태
- 프론트엔드 : 현행 유지. 나중에 디자인만 좀 더 이쁘게 하는 정도만 고민중.
- 백엔드 : GCP로 운영되는 백엔드. 메인 컨텐츠인 preview(방송에고), tweet(최신 트윗), notice(공식 소식)를 판정 및 제어하는 역할. v2에서는 필요에 따라 개발하다보니 메인 컨텐츠가 늘어남에 따라 텔레그램 제어계통 및 내부 처리 로직 등이 파편화되었다고 판단됨. 따라서 이번 v3에서 주요하게 손을 볼 예정. 백엔드 수술 후 v2와 호환이 안될 가능성이 높다고 판단하여 v3으로 가정하여 버전 업함.
- 업스트림 시스템 : 운영자 폰의 Automate 플로우. 트윗 푸시알림을 llamalab의 automate 앱을 통해 http request로 백엔드에게 POST하는 역할. 데이터 흐름상 백엔드 앞단에 있으며, 코드베이스 밖이라 런타임에서 직접 관측·버전관리는 안 됨(진짜 서드파티는 X·YouTube의 푸시알림 시스템이고, 이 폰 플로우는 그 신호를 중계하는 1st-party 노드). 현재 노드는 아래와 같이 구성됨. 이 구성을 유지하되, [notification posted?] 블록에서 삼성브라우저의 푸시알림만 받고 있는 상태인데, 추후 유튜브 알림도 함께 받아오게 할 수 있음. 왜냐하면 이를 통해 회원 전용 방송을 파악할 수 있는 가능성이 있기 때문.
    [flow begining]->[notification posted?]->[expression true?]->[variable set]->[http request]->[log append]
- 외부LLM : Groq LLM 서비스. v2에서는 없는 신규요소로 아직 v3에서 넣을지 말지 확정안남. 이를 추가하려는 이유는 notice할 때 정규표현식을 사용하기 때문에 제목이나 본문을 잘 캐치하지 못하기 때문. 이를 추가하게 되면 아키텍쳐는 복잡해지지만 부가적으로 notice의 제목과 개인 트윗을 번역하여 제공할 수 있음. 게다가 무료임.

# v3 - features

## Preview board (기존 방송예고)
- 이제 각 영상예고 아이템에 대하여 5개 상태를 부여하고자 함.
    * none : 기존의 none. 영상에 대한 아무 정보도 없으며 예고 아이템 실체도 없는 상태.
    * announced : 기존의 scheduled. 백엔드가 일정 주기로 감지하는 스케줄과 혼동될 여지가 있어 이름을 바꿈. 방송 예고가 감지되었으나 일부 정보만 파악된 상태를 말함. 최신 예고 정보가 이와 다르면 최신 예고 정보로 갱신. 프론트에는 현재 기준 scheduled가 표시하는 관례를 적용할 것.
    * upcoming : 기존의 upcoming. 방송 예고가 감지 + 정확한 날짜 + 시간 + 제목 + 썸네일 + url 모두를 파악한 경우 이 단계로 승격할 수 있음. 최신 예고 정보가 이와 다르면 최신 예고 정보로 갱신.
        - **유튜브 앱 알림 경로**: `LIVESTREAM_TUNEIN`(예정−30분) 알림 한 건으로 5필드가 다 채워진다 —
          `chime.slot_key`=video_id(온전한 11자) → url + 썸네일(`i.ytimg.com/vi/<id>/mqdefault.jpg`),
          `android.text`=제목, 날짜=당일, 시간=**알림 도착 + 30분**(파생값. 정확 ISO 아님 →
          provenance 를 남기고 이후 `REMINDER`/watching 이 정정). 즉 시작 전 승격 기회가 확정적으로 1회 온다.
        - 트윗 경로 예고(`announced`)에 이미지가 딸려 있으면 vxtwitter unfurl 로 썸네일을 얻어
          이 승격 조건의 "썸네일"을 만족시킨다(아래 업스트림 절 참조).
    * watching : 신설 단계. announced 또는 upcoming 상태에서 파악된 날짜/시간으로부터 3분 전 지금과 같이 모니터링하여 live 시작 시까지 관찰하는 단계. 
        지각(시작 시간 초과) 120분까지 아래와 같이 관찰.
            - 3분 단위로 live 상태인지 체크 
            - 최신 예고 정보 갱신 시 다시 upcoming 상태로 되돌아감.
            - 120분 경과 시 announced로 강등하되 url은 살릴 것. 추후 업데이트 시 해당 영상에 대한 언급인지 확인하기 위함임.
    * live : 실제 시작이 확인되면 첫 60분까지 10분마다 종료했는지 파악. 만약 시작 60분 경과 후 3분마다 종료 체크할 것. 종료가 확인되면 end 상태로 넘어감. '방송중(n분)'
    * end : 신설 단계. 종료 후 프론트 UI 상에서 ON-AIR이던 것을 OFF-AIR(빨간테두리 소등)으로 하고 '방송 종료'라고 표기하되 아직 영상 내리지말 것. 30분간 5분 간격으로 해당 유닛이 live아닌 상태(종료 상태)를 유지하면 none으로 이동하고 영상을 완전히 내림. 만약 다시 켠다면 live로 이동하고 바뀐 제목, 날짜/시각, url을 업데이트할 것. 마지막 30분째 이 아이템이 youtube 영상 형태가 아닌 예고 스트림으로 바뀌어졌다면 upcoming으로 다시 이동.
- 방송에고 아이템의 생애주기 : none -> announced -> (upcoming) -> (watching) -> live <-> end -> none
- **video_id 없는 assumed-live 폴백** (v2 핫픽스 → v3 계승): `announced`/`upcoming` 인데 `video_id` 를
  끝내 못 얻어 `watching`/`live` 로 못 넘어간 채 예정 시각만 지난 행은 종료를 검사할 주체가 없다.
  프론트엔 "방송 중(추정)" 으로 잠깐 뜨되 **예정 시각 + 90분**이면 자동으로 `none` 처리(영상/카드 제거).
  1번(유튜브 알림)이 승격을 거의 확정화하면 이 경우는 드물어지지만 폴백은 남긴다.
  v2 구현: `reconcile.ASSUMED_LIVE_MAX_SEC` — `assumed_live` + `video_id` 없음 + `scheduled_start+90분` → drop.
- 기타사항
    * '오늘' 영역인 것에 대해서는 지금처럼 'n시간 m분 전'이라고 표시.
    * '7일 이내' 영역에 대해서는 'D-n %H:%M'이라고 표시.
    * 그 외 영역에는 날짜/시각은 %Y-%m-%d %H:%M 형식으로 나타낼 것.
    * 이 기능은 프론트엔드에서 계산하여 렌더링할 것. (왜냐하면 현행과 같이 백엔드에서 처리하면 텍스트로만 받아들이므로 의도하고자 하는 형식이 깨지는 케이스가 발견되었기 때문.)

## Twit badge(기존 트윗)
- 지금의 트윗과 동일하나 필터링을 하고자 함.
- '@~~~:'로 시작하는 글과 같이 리트윗 등 본인이 게재한 글이 아니면 필터링.
- LLM을 사용하는 외부LLM가 붙으면 한글과 번역과 같이 제공할 예정.

## Notice board(기존 소식)
- 공식계정의 글 중 현재보다 미래인 이벤트에 대하여 날짜/시각, 제목, url을 파악하여 게재.
- 본문에서 제목을 찾아내기 어려워 외부LLM가 붙으면 이를 활용하여 제목을 잡아낼 예정. (번역도 함께 제공 예정)


# v3에서의 업스트림 시스템 고찰
- 현재는 내 폰에 뜨는 푸시알림을 통하여 트윗소식을 백엔드에 전달하고 있음.
- 장점은 무료라는 점과 이미 사용하고 있을 정도로 검증되었음. 단점은 트윗에서 함께 제공되는 이미지, 비디오 등 미디어는 제공불가능. 또한 본문·URL이 알림에서 잘려서 온다(`youtube.com/live/HkjQ3HJau…` 처럼 → video_id 복원 불가).
- X api나 vxtiwtter를 이용하면 단점 해소 가능. 만약 x api를 쓴다면 유료이지만 트윗관련해서 업스트림 시스템의 역할이 사라짐.
- 그러나 회원전용 영상에 대해서는 감지가 여전히 불가능함. 아직 확인이 필요하지만, youtube 알림을 이용하여 이와 같이 해결할 수 있다고 사료됨.

## 결정 (2026-09-08)

### 1. 유튜브 앱 알림 중계 추가
- 업스트림 폰 플로우에 유튜브 앱(`com.google.android.youtube`) 알림도 받는 플로우를 추가.
  현재는 로깅만(HTTP 스텝 없음, `ref/flow-7 (4).log` 09-08 19:32~). 관찰 결과 payload 는 아래를 준다:
    - `chime.slot_key` = **video_id (온전한 11자)** — 트윗 경로의 잘린 URL 문제를 우회. 이게 핵심.
    - `pde_noti_tag` = `<video_id>::<uuid>` (SUMMARY 항목은 `<hash>::SUMMARY::<n>` → 버림)
    - `android.text` = 방송 제목(풀텍스트). `android.title` 은 잘림("🔴 30분 후에 …") — 쓰지 말 것.
    - `chime.thread_id` 접두어로 알림 종류: `NOTIFICATION_TYPE_LIVESTREAM_TUNEIN`(예정−30분),
      `..._LIVESTREAM_REMINDER`(=예약분 시작), `..._SUBSCRIPTION_LIVESTREAM_START`(구독 채널 시작).
    - `android.subText` = `null` (트윗 릴레이는 `x.com` → 라우팅 시 이걸로 X/YT 구분 가능).
    - 이미지: `android.largeIcon`/`android.pictureIcon` 는 `null` (`android.reduced.images=1` 로 비트맵 제거됨).
      썸네일은 video_id 로 조립 (`i.ytimg.com/vi/<id>/mqdefault.jpg` — 항상 존재·16:9·검은띠 없음).
- 용도:
    - **video_id 확보** → 공개 방송은 정규 파이프라인(videos.list/reconcile/watching)이 그대로 처리.
    - `announced → upcoming` 승격(위 Preview board 절). `TUNEIN` 이 예정−30분이라 시작 전 승격이 확정적.
    - 회원전용: videos.list 는 404 → API wake 사이클을 태우지 말고, 알림만으로 카드 구성 +
      video_id 없는 assumed-live 90분 폴백에 의존. 프론트에 "회원전용" 배지.
- **미확인 (모니터링 중)**: 회원전용 방송 알림이 실제로 오는지 + payload 가 위와 동일한지.
  대상 채널(개인 5인) 알림 샘플도 아직 없음 — 로그 나오면 확인 후 확정.

### 2. vxtwitter unfurl 도입
- 업스트림이 트윗을 릴레이할 때 이미 `pde_noti_tag` 에서 트윗 Snowflake id 를 뽑고 있음
  (`xtweet` 가 merge 정렬에 사용). 이 id 로 `https://api.vxtwitter.com/i/status/<id>` 조회 → JSON.
- 해소되는 것: (a) 개인 트윗 배지의 첨부 **이미지**, (b) **잘리지 않은 본문 + 온전한 `youtube.com/live/…` URL**
  → video_id → 썸네일 + 정규 live/end 추적(= 유노 유령 라이브 버그가 애초에 안 남), (c) 개인 트윗
  예고가 이미지를 포함하면 그 이미지를 `announced` 아이템 썸네일로 → upcoming 승격 조건 충족에도 기여.
- 텔레그램 링크프리뷰 이미지를 재활용하는 방안은 폐기: Bot API 가 프리뷰 이미지를 file_id/URL 로
  안 돌려주고, X 가 프리뷰 크롤러를 막아 실패율이 높으며 비결정적. vxtwitter 가 결정적이고 상위호환.
- 리스크: 서드파티 무료 서비스(가동률 보장 없음, ToS 회색지대). 트래픽 5계정·하루 몇 건 수준이라
  감수. 불안정하면 fxtwitter 셀프호스팅으로 대체 가능. **계정 밴 위험 없음**(읽기 전용, 인증 불필요).


# telegram 명령어 계통의 정리 필요

## 일반
- /log : 지금과 같은 로깅 레벨 설정.
- /status : 백엔드의 상태(pause 여부, contents의 각각 개수, 업데이트 시각 등, 마지막 동기화 시각, 다음 동기화 시각 등)
- /pause : 백엔드 일시중지
- /resume : 백엔드 재개

## 메인컨텐츠 제어
* contents : preview / notice / tweet 중 1개 선택.
- /list [contents] : 해당 컨텐츠의 idx와 제목, 상태 등 표시.
- /ingest [contents] : 기존 ingest처럼 원문을 붙여달라고 요청하고, 원문 전달받으면 ingest 수행.
- /edit [contents] : /list를 실행하여 해당 컨텐츠의 정보 제시 후 어떤 idx를 수정할지 지금처럼 되묻기. idx 응답받으면 각 컨텐츠의 항목을 하나씩 되물어보고 완성하여 반영하기.
- /edit -i [idx] [contents] : 해당 컨텐츠의 idx번째 아이템에 대하여 ingest 방식으로 편집함. 수정된 원문을 붙여달라고 요청하기.
- /del [contents] : /list를 실행하여 해당 컨텐츠의 정보 제시 후 어떤 idx를 지울지 되묻기.
- /undo : 방금한 동작을 되돌림.


# 외부LLM의 역할
- Groq이 서빙하는 LLM을 활용.
- notice에서의 활용 : 날짜/시간, url을 정규표현식을 이용하여 우선 파싱 -> 원문에서 날짜/시간, url 제거 후 제목을 파싱. 번역도 함께 제공 에정.
- tweet에서의 활용 : 개인 유닛 5명의 트윗을 받았다면 이를 번역하도록 함. 사용자는 말풍선 또는 메시지 창에서 토글버튼을 통해 원문-번역으로 볼 수 있음.

## 모델 선정 (2026-09-09)

- **주 모델: `openai/gpt-oss-120b`** — 형제 프로젝트 bandori-playlist-maker 에서 쓰던 것 그대로.
  프롬프트·클라이언트 코드 재활용 가능, JP 독해·KO 출력 품질 충분, 지시이행/구조화 출력 강함(~500 tok/s).
- **폴백: `llama-3.3-70b-versatile`** — 다른 계열·프로덕션·JSON 모드 지원. 주 모델이 429/5xx 뱉을 때 스위치.
- **preview 모델(qwen3-32b·kimi-k2 등) 금지** — Groq preview 는 예고 없이 내려가 파이프라인이 깨진다.
  프로덕션 티어 모델만 사용(현재 채팅용 프로덕션 = gpt-oss-120b/20b, llama-3.3-70b, llama-3.1-8b).
- **호출 형태**: notice 는 제목추출 + 번역을 **JSON 1회 호출**로 (`{"title_ja","title_ko",...}`).
  구조화 출력은 gpt-oss 계열이 `response_format` 의 `json_schema` 까지, llama-3.3 은 `json_object` 지원.
- gpt-oss 는 reasoning 모델 → 이 난이도엔 `reasoning_effort:"low"` 고정(지연·토큰 절감), 번역이 아쉬우면 `medium`.
- **무료티어**: notice·개인트윗은 하루 수 건이라 RPM/RPD 한도에 근처도 안 감. 429 대비 지수백오프 재시도만.


# 데이터 브랜치에 관하여
- 기존 데이터들은 .old/ 폴더 안으로 이동.
- v3의 데이터 스키마에 맞춰 재구성할 것.

# 기타
- 방금 업스트림 시스템(폰)에서 Youtube 앱에서 푸시알림이 뜨는 것을 확인.
- 그러나 개인 유닛 외의 다른 채널도 구독해놓았기 때문에 방금 온 것은 대상 채널이 아니었음.
  이 푸시알림의 키값은 `ref/flow-7 (4).log` 로 확인됨 → 위 "업스트림 시스템 고찰 §1" 에 정리.
  요점: `chime.slot_key`=video_id, `android.text`=제목, `chime.thread_id`=알림종류, 이미지 비트맵은 제거됨(썸네일은 video_id 로 조립).
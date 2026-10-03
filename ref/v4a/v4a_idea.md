# 핵심 기능

## 업스트림
- X push 수신 시
    - 발신자가 공식 채널
        1) 예고(preview)
        2) 소식(notice)
    - 발신자가 개인 멤버
        1) 예고(preview)
        2) 트윗(tweet)

- YT push 수신 시
    - 발신자가 공식 채널 | unit
        1) 예고


## preview 관리
- 공식 채널로부터 트윗 알림받은 경우
    1) 예고 관련글인지 확인.
    2) 예고가 맞다면 unit[arale, yuno, ...], date, url을 파싱. 예고가 아니라면 draw.
    3) url이 존재한다면 videos.list로 필요 정보를 모두 수집 및 업데이트한 후 upcoming으로 등록. (단, url은 해당 unit의 채널 url이 아닌 영상 url을 의미.)
       만약 url이 없다면 제공된 정보만으로 announced 등록.
- unit 트윗 알림을 받은 경우
    1) 예고 관련글인지 확인.
    2) 예고가 맞다면 title, date, url, thumbnail을 수집.
    3) url이 존재한다면 videos.list로 필요 정보를 모두 수집 및 업데이트한 후 upcoming으로 등록. (단, url은 해당 unit의 채널 url이 아닌 영상 url을 의미.)
       만약 url이 없다면 제공된 정보만으로 announced 등록.
- YT로부터 알림을 받은 경우
    1) 발신채널이 unit 또는 공식YT채널인지 확인. 아니라면 draw.
    2) 시작 30분 전 알림이면 url을 파악 후 upcoming 등록.
       만약 시작 알림이면 url을 파악 후 live 등록.
- 등급 관리('~~'는 필수요소)
    - announced : 'date', title만 있는 단계. 
    - upcoming : 'url', date, title이 있는 단계.
    - watching : upcoming이 예고한 시각 20분 전 or YT push로부터 30분 전 알림이 온 경우.
    - live : watching이 YT push로부터 시작 알림을 받은 경우.
    - end : 현행 로직대로 폴링하여 liveBroadcastContent="none"으로 나오면 end로 전환. 30분간 5분 간격으로 동일 url이 라이브 상태가 되는지 보고, 라이브가 되면 다시 live로 진입. 프론트 UI에서는 end 상태이면 '방송 종료'라고 표시할 것. 만약 다른 url의 영상이 live 상태가 되면 프론트 UI에서는 live를 우선적으로 표시할 것.
    - none : 이 단계는 특별한 역할이 없어서 삭제 고려.


## notice 관리
- 공식 채널로부터 트윗 알림을 받은 경우
    1) if not 리트윗 & not 예고, 현행 로직과 같이 번역하여 소식에 등록.

## tweet 관리
- unit으로부터 트윗 알림을 받은 경우
    1) 리트윗이 아니라면 현행과 같이 번역하여 tweet에 등록.
- 보존 시간을 24시간 -> 48시간으로 늘릴 것.


# 부가 기능

## 모니터링 시스템
- 현행 유지. 

## 제어 시스템
- 관리자 웹UI를 통해 기존 DM 명령어(ingest, edit, del 등) 수행
- status, pause, resume, list 등의 명령어만 DM 유지


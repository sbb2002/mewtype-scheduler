# 라이브 알림 실험실 (test/live-notify)

시험 전용 최소 구현. 배포 · `main` 병합 대상 아님.

```bash
pip install pywebpush          # cryptography · py-vapid 같이 들어옴
python lab/push/server.py      # 저장소 루트에서
```

- 팬 화면 `http://localhost:8770/` — 실제 프론트(`src/frontend`). 네임플레이트 핸들 옆 종 = 멤버 알림, upcoming · watching 카드의 종(오늘 카드 썸네일 왼쪽 아래 · 이후 예고 카드 오른쪽 아래 · PC 타임테이블 팝업) = 그 방송 알림.
- 경과 · 결정 · 남은 일 = devpapers `ref/live-notify/HANDOFF.md`.
- 서버 보기 `http://localhost:8770/lab` — 방송 상태 바꾸기(→ live 면 발송) · 등록 현황 · 서버 기록 · 버스트 시험.
- `/data/preview.json` 은 실험실 사본(시작 때 운영 data 브랜치에서 받아 옴), 나머지 `/data/*.json` 은 운영 것을 중계.
- 구독 저장 · VAPID 키는 `lab/push/.data/`(gitignore).

## 동작

- 프론트: 종을 누르면 화면이 즉시 바뀌고(localStorage 「켠 멤버 · 등록 영상」), **마지막 조작 뒤 2초 조용하면 최종 상태 1건만** `POST /push/state` — 연타 방어는 프론트 몫.
  페이지를 열 때마다 한 번 다시 보내고, 오류는 화면에 안 알리고 간격을 늘려 다시 보낸다.
- 서버: **응답은 늘 202**(팬 화면은 어떤 경우에도 같다). 크기 초과 · 형식 오류는 조용히 버림.
  저장소 = Firestore 를 흉내 낸 로컬 문서 저장소(`DocStore` — 구독 1개 = 문서 1개, 문서 id = 푸시 주소 해시). get · set · delete · `array-contains-any` 조회만 쓴다.
  내용이 같으면 쓰지 않음(읽기 1건). 하루 쓰기 상한(기본 1만, 쓰기 + 삭제, 태평양 시간 자정 기준 = Firestore 무료 한도 기준) 넘으면 그날은 안 씀.
  멤버 · 영상이 둘 다 비면 해지(문서 삭제).
- 발송: 방송이 live 가 되는 순간 조회 2번(그 멤버를 켠 문서 + 그 영상을 등록한 문서) → Web Push(TTL 30분). 영상당 한 번. 404/410 이면 문서 삭제.
- 실제 Firestore 어댑터는 아직 없음 — 로컬 에뮬레이터에 Java + `gcloud components install cloud-firestore-emulator` 가 필요(이 PC엔 Java 없음).

## 아직 정하지 않은 것(운영자 결정 대기)

- 방송을 새로 판 경우(새 video_id) 등록 승계 · 다시 알릴지 — 미구현
- 회원 전용 방송도 알릴지 — 지금은 알림(기록에 「회원 전용」 표시)
- PC 오늘 타임테이블 이름 자리 종 — 미구현

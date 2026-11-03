from pathlib import Path
import json,tempfile
R=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/hotfix-birthday-player-controls')
O=Path(tempfile.gettempdir())/'birthday-player-ui'
ui=json.loads((O/'results.json').read_text(encoding='utf8'));monitor=json.loads((O/'monitor/results.json').read_text(encoding='utf8'));life=json.loads((O/'lifecycle.json').read_text(encoding='utf8'))
assert len(ui)==4 and all(not x['errors'] and x['drag'] and x['normal_shortcuts_disabled'] for x in ui.values())
assert all(not x['errors'] and x['temporary_AB_labels'] and x['labels_restored'] for x in monitor.values())
assert monitor['android-touch']['inside_touch_swipe'] and not life['errors']
rows='\n'.join(f"| {k} | {v['greeting']['en']['size']:.2f} / 800 | {v['greeting']['who']['size']:.2f} / 700 | 통과 |" for k,v in ui.items())
doc=f'''# 생일 UI 핫픽스 검증 — v4.11.1 (2026-11-01)

운영자가 핫픽스 등급과 검증 후 병합·배포를 지정한 수정이다. 백엔드·음원·장면 Canvas 수식은 변경하지 않았다.

## 요청 반영

- 인사말의 크기·굵기·그림자를 강화했다. 공개/퇴장 시각은 유지한다.
- 마우스가 플레이바 위에 있는 동안만 바탕과 전체 불투명도 100%를 적용한다. 유휴 5초가 지나도 호버 중에는 흐려지지 않고, 벗어나면 기존 유리 반투명 바탕으로 돌아간다. 터치의 잔류 hover로 불투명해지지 않는다.
- 왼쪽 끝 6점 손잡이로 마우스·터치 이동한다. 재생/볼륨 조작은 이동을 시작하지 않는다. 화면 경계·하단 안내를 피하고 모바일의 제목도 따라간다. 창 크기 변화·회전 시 재제한, 키보드 이동/Home 복원, 방문 내 위치 유지와 정리를 구현했다.
- 일반 화면의 생일 음악 재생 버튼과 생일 단축키를 제거/제한했다. 음악은 계속 재생하고 생일 화면의 플레이바에서 조작한다.
- 방향 입력 완료 후 APP=A, EXT=B로 잠시 표시한다. 두 탭이 빛나고 다음 입력(B→A)을 더 강하게 강조한다. 완료/취소/틀린 탭/만료에는 원래 이름·너비·접근성 이름과 스타일을 복원한다. iframe 교체도 처리한다.
- 모바일은 팝업 안쪽에서 주축으로 36px 이상 밀면 인식한다(주축이 다른 축의 1.25배 이상). 좌우 경계 밖까지 나갈 필요가 없다. 마우스의 기존 바깥 경계 입력은 유지한다.

## 실행한 검사

`Get-ChildItem src/frontend/js/*.selfcheck.mjs | ForEach-Object {{ node $_.FullName }}`: 11개 모두 통과.

`python scripts/verify_birthday_player_ui.py`: 실제 마우스/CDP 터치, 최초 인사말 표시와 화면 안 배치, 손잡이 이동·위/아래/좌/우 제한, 재생·볼륨 보존, 호버 5.2초 유지, 키보드/Home, 일반 화면 키 차단·재생 유지, 재진입 위치 유지, 회전·정리 검사 통과. JS pageerror 0.

| 화면 | 인사말 크기(px) / 굵기 | 이름·날짜 크기(px) / 굵기 | 배치·조작 |
|---|---:|---:|---|
{rows}

`python scripts/verify_monitor_birthday.py`: PC 마우스·Android 터치에서 네 방향 표시, 팝업 안쪽 44px 입력(36px 기준), A/B 이름과 빛, B→A 진입, 잘못 누른 탭·30초 만료 후 복원, 라이브 실패→스냅샷 iframe 교체 뒤 재적용, 저장값 보존·정상 초기화를 검사했다. JS pageerror 0.

`python scripts/verify_birthday_lifecycle.py`: 실제 자동재생 차단→터치 시작, 음소거·저장 볼륨, 자연 곡 경계(gap 0), 정지 탐색 오차 0, 자정/정리 후 Audio·AudioContext·blob·RAF 0, destroyBirthday 후 생일 소유 리스너 0. 새 손잡이 리스너와 관찰자도 정리한다.

산출물은 운영자 PC 임시 폴더 `{O}`의 results/monitor/lifecycle JSON, selfchecks 로그와 화면 PNG다. 실제 삼성 브라우저·iPhone의 하드웨어/브라우저 음향·터치 체감은 운영자 후속 확인 대상이며 에뮬레이션을 실기기 검증으로 간주하지 않는다. 배포 식별자와 롤백은 `docs/VERSION.md`에 완료 뒤 기록한다.
'''
(R/'docs/BIRTHDAY_PLAYER_HOTFIX_VERIFICATION.md').write_text(doc,encoding='utf8',newline='\n')
p=R/'docs/VERSION.md';s=p.read_text(encoding='utf8');s=s.replace('실제 삼성/iPhone은 운영자 확인 대상.','실제 삼성/iPhone은 운영자 확인 대상. 상세: `docs/BIRTHDAY_PLAYER_HOTFIX_VERIFICATION.md`.',1);p.write_text(s,encoding='utf8',newline='\n')
p=R/'docs/SPEC.md';s=p.read_text(encoding='utf8').replace('일반 화면에는 음악 재생 버튼을 두지 않고','일반 화면에는 생일 음악 재생 버튼을 두지 않고');p.write_text(s,encoding='utf8',newline='\n')
p=R/'scripts/verify_monitor_birthday.py';s=p.read_text(encoding='utf8').replace("json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8'", "json.dumps(results,sort_keys=True,ensure_ascii=False,indent=2)+'\\n',encoding='utf8'");p.write_text(s,encoding='utf8',newline='\n')
body='''생일 화면 인사말을 크게·굵게 바꾸고 플레이바 마우스 호버 시 불투명하게 표시합니다. 왼쪽 손잡이로 드래그/터치 이동하고, 일반 화면의 생일 재생 버튼은 제거합니다.

모니터 방향 입력 완료 뒤 APP=A, EXT=B를 잠시 표시·강조하며 B→A로 진입합니다. 모바일은 팝업 안쪽의 36px 스와이프로 입력할 수 있어 좁은 좌우 여백에 막히지 않습니다. 만료·취소·잘못 누른 탭은 이름과 스타일을 복원합니다.

- 운영자 지정 핫픽스 v4.11.1. 프론트만 변경.
- self-check 11개, PC/390·360·320px 플레이바 조작/회전/호버/정리 검사 통과.
- PC·Android 터치의 모니터 진입·A/B 표시/복원·iframe 교체 검사 통과.
- 기존 자동재생/음소거/곡 경계/자정·리스너 정리 검사 통과. JS pageerror 0.
- 실제 삼성/iPhone의 체감 확인은 운영자 후속 확인 대상. 롤백 2ee9cc7(v4.11.0).

상세: docs/BIRTHDAY_PLAYER_HOTFIX_VERIFICATION.md. 기존 열린 문서 PR #122/#124는 포함하지 않습니다.
'''
Path(__file__).with_name('player-hotfix-pr-body.md').write_text(body,encoding='utf8')
print('검증 수치 확인·문서·PR 설명 작성 완료')

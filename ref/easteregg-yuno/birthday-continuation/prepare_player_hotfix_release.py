from pathlib import Path
import re,json,shutil,tempfile
R=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/hotfix-birthday-player-controls')
def change(name,fn):
 p=R/name;p.write_text(fn(p.read_text(encoding='utf-8-sig')),encoding='utf8',newline='\n')
def spec(s):
 s=s.replace('한 번 누르고 뗄 때 한 방향만 입력한다. 실제 이동 24px 이상이며 창 경계에서 12px 이상 벗어났을 때 인식하고', '한 번 누르고 뗄 때 한 방향만 입력한다. 마우스는 실제 이동 24px 이상·창 밖 12px 이상에서 인식한다. 모바일은 팝업 안쪽에서 36px 이상 움직이고 주축 이동이 다른 축의 1.25배 이상이면 인식하므로 화면 밖으로 밀 필요가 없다. 입력을 인식하면')
 s=s.replace('이후 같은 리포트 iframe의 EXT → APP 탭을 차례로 누르면', '이후 같은 리포트 iframe의 EXT → APP 탭을 차례로 누르면')
 s=s.replace('이어 리포트 iframe의 EXT → APP 탭을 차례로 누르면', '이때 APP는 A, EXT는 B로 잠시 이름만 바꾸고 두 탭을 빛나게 한다. 다음 입력인 B(EXT)를 더 강하게 표시하고 누르면 A(APP)가 더 강해진다. 이어 B(EXT) → A(APP)를 차례로 누르면')
 s=s.replace('진입 입력은 저장값을 지우지 않으며 드래그 뒤의 호환 click도 소비한다.', '진입 입력은 저장값을 지우지 않으며 드래그 뒤의 호환 click도 소비한다. 완료·취소·만료·틀린 탭에서는 APP/EXT 이름과 기존 접근성 이름·너비를 복원하고 강조 스타일을 제거한다. iframe 교체 시에도 준비 상태의 A/B 이름과 강조를 새 문서에 적용한다.')
 s=s.replace('Space/좌우/상하/M 단축키, 모바일 슬라이더', '생일 전체 화면에서만 Space/좌우/상하/M 단축키, 모바일 슬라이더')
 return s
change('docs/SPEC.md',spec)
change('docs/BIRTHDAY_MUSIC_SCENE_SPEC.md',lambda s:s.replace('🎂 버튼 옆에 작은 재생/정지 아이콘만 표시.', '일반 화면의 작은 재생/정지 아이콘은 제거한다(2026-11-01 운영자 수정). 재생 조작은 생일 전체 화면 컨트롤에서만 한다.').replace('1. 일반 화면에서도 음악 재생 + 🎂 옆 작은 재생/정지 아이콘.', '1. 일반 화면에서도 음악 재생은 유지하되 작은 재생/정지 아이콘은 제거한다(2026-11-01 수정).').replace('키보드: Space 재생/정지', '생일 전체 화면의 키보드: Space 재생/정지').replace('- **하단 컨트롤**: 유리 알약(반투명 + blur) = 이전곡', '- **하단 컨트롤**: 유리 알약(반투명 + blur, 마우스 호버 중 불투명) = 왼쪽 이동 손잡이 · 이전곡'))
change('docs/BIRTHDAY_SKIN.md',lambda s:s.replace('창 밖으로 ↑, ↑, ↓, ↓, ←, →, ←, → 순서로', '↑, ↑, ↓, ↓, ←, →, ←, → 순서로').replace('드래그하거나 터치해 밀어낸다. 방향을 인식한 가장자리가 빛난다.', '드래그하거나 터치해 민다. 마우스는 창 밖으로, 모바일은 창 안쪽에서 약 36px만 밀어도 된다. 방향을 인식한 가장자리가 빛난다.').replace('리포트의 EXT 탭, APP 탭을 차례로 누른다.', '리포트의 APP/EXT가 잠시 A/B로 바뀌고 빛난다. B(EXT), A(APP)를 차례로 누른다.').replace('틀린 탭이나 30초 무입력은 준비 상태를 취소한다.', '틀린 탭이나 30초 무입력은 준비 상태를 취소하고 탭 이름을 원래대로 복원한다.')+'''
### 플레이바·진입 보완 (v4.11.1, 운영자 지정 핫픽스)

- 인사말은 큰 영문 800 굵기, 이름/날짜 700 굵기와 진한 그림자로 읽기 쉽게 조정했다. 공개 시각은 유지한다.
- 플레이바 왼쪽 끝의 6점 손잡이로 마우스/터치 이동한다. 화면 경계와 하단 안내를 피하고 모바일 곡 제목은 위를 따라간다. 손잡이 포커스에서 방향키(8px, Shift 32px), Home 기본 위치 복원도 가능하다. 위치는 이번 방문 동안 유지한다.
- 마우스를 올린 동안만 플레이바를 불투명하게 하고 벗어나면 기존 반투명 표시로 돌아간다. 일반 화면의 작은 재생 버튼을 제거하고 생일 음악 단축키도 전체 화면에서만 동작한다. 음악 재생은 일반 화면에서도 이어진다.
- 모바일 방향 입력은 팝업 밖으로 나갈 필요 없이 창 안의 짧은 한 방향 스와이프로 된다. 방향 완료 뒤 임시 A/B 이름·탭 강조도 추가했다. 실제 삼성 브라우저의 후속 체감 확인은 운영자가 진행한다.
''')
change('docs/TERMINOLOGY.md',lambda s:s.replace('초기화 확인창 안에서 창 밖으로 ↑↑↓↓←→←→를 드래그·터치하고, 창이 닫힌 뒤 EXT → APP 탭으로', '초기화 확인창에서 ↑↑↓↓←→←→를 드래그·터치하고(모바일은 안쪽 36px도 인식), 창이 닫힌 뒤 임시 B(EXT) → A(APP) 탭으로'))
change('src/frontend/js/config.js',lambda s:s.replace('APP_VERSION = "v4.11.0"','APP_VERSION = "v4.11.1"'))
change('README.md',lambda s:s.replace('현재 버전: v4.11.0 (마이너 · 2026-11-01)','현재 버전: v4.11.1 (일반 패치 · 2026-11-01)'))
change('CLAUDE.md',lambda s:s.replace('현재 버전 = v4.11.0 (마이너, 2026-11-01)','현재 버전 = v4.11.1 (일반 패치, 2026-11-01)').replace('bdayaudio.js bdayplayer.js bdayguard.js', 'bdayaudio.js bdayplayer.js bdayplayerdrag.js bdayguard.js'))
def version(s):
 i=s.index('- **v4.11.0**')
 entry='''- **v4.11.1** (일반 패치·핫픽스, 2026-11-01 — 브랜치 `hotfix/birthday-player-controls`, 프론트만): **생일 인사말·플레이바와 모바일 모니터 입력 보완.** 운영자가 이번 수정을 핫픽스 등급으로 지정했다.
  - 인사말 영문/이름·날짜를 확대·굵게 하고 대비를 높였다. 플레이바 마우스 호버 중 불투명, 그 외에는 기존 반투명이다.
  - 왼쪽 6점 손잡이로 마우스·터치 이동한다. 화면 경계/안전영역/하단 안내를 피하고 모바일 곡 제목도 따라간다. 방향키 이동·Home 복원, 화면 회전 후 재제한, 방문 내 위치 유지와 정리를 지원한다.
  - 일반 화면의 작은 재생 버튼을 제거하고 생일 단축키를 전체 화면으로 제한했다. 일반 화면에서도 음악은 이어진다.
  - 모니터의 방향 완료 뒤 APP=A, EXT=B로 잠시 바꾸고 두 탭과 다음 입력을 강조한다. B→A로 진입하며 만료/취소 시 원래 이름·스타일을 복원한다. 모바일은 팝업 안에서 36px 스와이프로 네 방향을 입력하므로 좁은 좌우 여백의 영향을 받지 않는다.
  - **검증**: self-check 11개, 새 플레이바 UI 검사(1440×900 PC, 390×844·360×800·320×740 터치, 회전·호버 유지·일반 화면 조작 차단), PC/Android 모니터 명령·A/B 이름 복원·팝업 안쪽 입력, 기존 자동재생·곡 경계·자정/정리 검사 통과. 실제 삼성/iPhone은 운영자 확인 대상.
  - **배포 진행**: 사용자 승인으로 검증 후 병합·프로덕션 배포한다. 완료 뒤 병합 커밋·태그·Vercel 식별자를 기록한다. 롤백 = `2ee9cc7`(v4.11.0 완료 main). 백엔드·음원·장면 Canvas 수식 변경 없음.
'''
 return s[:i]+entry+s[i:]
change('docs/VERSION.md',version)
out=Path(tempfile.gettempdir())/'birthday-player-ui'
shutil.copytree(Path(tempfile.gettempdir())/'birthday-verify-third/monitor',out/'monitor',dirs_exist_ok=True)
lifecycle=Path(r'C:/Users/User/AppData/Local/Temp/claude/C--Users-User-Documents-pyworks-mewtype-scheduler/cd557148-9ec6-47cb-b90f-a459b94aa233/scratchpad/handoff/verify/lifecycle.json')
shutil.copyfile(lifecycle,out/'lifecycle.json')
print('핫픽스 v4.11.1 문서·버전과 여섯 요청 반영')

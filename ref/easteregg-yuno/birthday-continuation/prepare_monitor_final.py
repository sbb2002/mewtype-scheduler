from pathlib import Path
import json,hashlib
B=Path(__file__).parent;D=B/'monitor-delivery';R=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
p=D/'scripts/verify_monitor_birthday.py';s=p.read_text(encoding='utf8')
s=s.replace(' def log_message(self,*a):pass', ''' def log_message(self,*a):pass
 def copyfile(self,source,outputfile):
  # 생일 화면 진입 직후 다음 검사로 이동하면 진행 중 음원 요청이 정상 취소될 수 있다.
  try:super().copyfile(source,outputfile)
  except (BrokenPipeError,ConnectionResetError):pass''')
p.write_text(s,encoding='utf8',newline='\n')
name='docs/BIRTHDAY_MUSIC_SCENE_VERIFICATION.md';s=(R/name).read_text(encoding='utf8')+'''
## 모니터 진입 후속 요청 검증 (2026-11-01)

`monitor.html` 초기화 확인창에서 ↑↑↓↓←→←→를 창 밖으로 드래그/터치하면 각 방향 가장자리가 빛난다. 8방향을 마치면 초기화 버튼이 빛나고 창이 닫히며, 리포트의 EXT→APP으로 `./?bday=yuno`에 들어간다. 저장값을 지우지 않는다. 사용 순서는 `BIRTHDAY_SKIN.md` 「모니터에서 시험 화면 열기」를 따른다.

- 순수 검사 11개 전체 통과(기존 10개 + 새 모니터 명령 검사).
- `python scripts/verify_monitor_birthday.py` 통과. 1440×900 마우스와 390×844 Android 터치에서 네 가장자리 빛·버튼 빛·팝업 닫힘·실제 생일 페이지 이동을 확인했다. 터치는 CDP의 실제 touchStart/touchMove/touchEnd로 입력했다.
- 잘못된 방향/탭, 30초 무입력, 라이브 실패→스냅샷 교체 뒤 새 iframe의 탭 연결을 검사했다. 진입 전 생일 음원/장면 자원 요청 0, 진입 뒤 저장값 유지, 정상 되돌리기 버튼의 저장값 초기화도 확인했다. JS pageerror 0.
- 모니터 리포트는 제품의 `monitor_report.render_html`에 빈 테스트 이벤트를 넣어 생성했다. 운영 로그/실데이터를 쓴 캡처는 아니다. 백엔드 소스·배포는 변경하지 않았다.
- 실제 삼성 브라우저는 미확인이다. SamsungBrowser UA·Android 터치 에뮬레이션을 실기기 검증으로 간주하지 않는다. 실제 iPhone Safari 미확인도 유지한다.

산출물은 새 검사 출력 폴더의 `monitor/results.json`, `pc-mouse-edge-*.png`, `android-touch-edge-*.png`, `*-armed.png`에 있다. 가장자리 표시는 드래그 중 즉시 켜지고 손을 뗀 뒤 450ms 유지된다. 방향 입력은 확인창 안에서 시작해야 하며 버튼에서는 시작하지 않는다.
'''
p=D/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf8',newline='\n')
m={}
for p in D.rglob('*'):
 if p.is_file():
  n=p.relative_to(D).as_posix();m[n]=hashlib.sha256((R/n).read_bytes()).hexdigest() if (R/n).exists() else None
(B/'monitor-manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8')

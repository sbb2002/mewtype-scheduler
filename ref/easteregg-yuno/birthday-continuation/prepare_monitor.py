from pathlib import Path
import json,hashlib
B=Path(__file__).parent;D=B/'monitor-delivery';R=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
def save(name,s):
 p=D/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf8',newline='\n')
def read(name):return (R/name).read_text(encoding='utf8-sig'.replace('utf8','utf-8'))
s=read('src/frontend/monitor.html')
style='''    /* 숨은 생일 진입: 방향을 인식한 변과 명령이 준비된 초기화 버튼을 밝힌다. */
    #reset-dlg[open] .dlg-in { touch-action: none; user-select: none; -webkit-user-select: none; }
    #reset-dlg::after { content: ""; position: absolute; pointer-events: none; opacity: 0; border-radius: 4px;
                         background: #8ae3e2; box-shadow: 0 0 8px #8ae3e2, 0 0 18px #ff488d; transition: opacity .12s; }
    #reset-dlg[data-bday-edge]::after { opacity: 1; }
    #reset-dlg[data-bday-edge="U"]::after { top: 3px; left: 14px; right: 14px; height: 3px; }
    #reset-dlg[data-bday-edge="D"]::after { bottom: 3px; left: 14px; right: 14px; height: 3px; }
    #reset-dlg[data-bday-edge="L"]::after { left: 3px; top: 14px; bottom: 14px; width: 3px; }
    #reset-dlg[data-bday-edge="R"]::after { right: 3px; top: 14px; bottom: 14px; width: 3px; }
    .rb.bday-armed { color: #ffb9d4; border-color: #ff68a0; box-shadow: 0 0 9px #ff488d, 0 0 18px #7844ba;
                     animation: bday-ready 1.5s ease-in-out infinite alternate; }
    @keyframes bday-ready { to { box-shadow: 0 0 14px #ff488d, 0 0 24px #8ae3e2; } }
'''
s=s.replace('    @media (prefers-reduced-motion: reduce) {',style+'    @media (prefers-reduced-motion: reduce) {')
s=s.replace('      .rb { transition: none; }', '      .rb { transition: none; }\n      .rb.bday-armed { animation: none; }\n      #reset-dlg::after { transition: none; }')
s=s.replace('</body>', '''  <script type="module">
    import { mountMonitorBirthday } from './js/monitorbirthday.js';
    mountMonitorBirthday();
  </script>
</body>''')
save('src/frontend/monitor.html',s)
s=read('docs/SPEC.md')
s=s.replace('실기기 미확인) — `src/frontend/monitor.html` 만', '실기기 미확인) — `src/frontend/monitor.html` · `js/monitorbirthday*.js`')
needle='- 백엔드 · 관리 페이지 · 텔레그램은 바뀌지 않는다(`monitor_report.py` 무수정).'
addition='''- **모니터 생일 진입 명령**(후속 추가 2026-11-01): 초기화 확인창의 버튼을 제외한 안쪽에서 마우스 왼쪽 드래그 또는 한 손가락 터치를 시작해 창 밖으로 `↑↑↓↓←→←→` 순서로 밀어낸다. 한 번 누르고 뗄 때 한 방향만 입력한다. 실제 이동 24px 이상이며 창 경계에서 12px 이상 벗어났을 때 인식하고 해당 변이 즉시 시안/분홍빛으로 빛난다(손을 뗀 뒤 450ms 유지). 모서리는 먼저 통과한 변으로 계산한다. 8방향을 마치면 상단 초기화 버튼이 빛나며 확인창이 닫힌다. 이어 리포트 iframe의 EXT → APP 탭을 차례로 누르면 같은 창의 `./?bday=yuno`로 이동한다(`va` 쿼리는 있으면 유지). 생일이 아닌 날에도 유노 인트로를 시험할 수 있다.
- **진입 명령 수명·안전**: 상태는 메모리에만 둔다. 잘못된 방향은 다음 ↑↑ 접두사부터 다시 인식하고, 준비 뒤 잘못 누른 탭·30초 무입력·확인창 다시 열기·취소/Esc·탭 숨김·페이지 이탈에서는 초기화한다. 진입 입력은 저장값을 지우지 않으며 드래그 뒤의 호환 click도 소비한다. 기존 되돌리기는 명시적으로 버튼을 클릭했을 때만 실행된다. Pointer Events/캡처와 `touch-action:none`으로 마우스·모바일 터치를 처리하고 다중 터치·pointercancel은 현재 동작을 버린다. 동작 줄이기에서는 가장자리 표시를 유지하되 버튼 점멸은 생략한다.
- **iframe 탭 연결**: 같은 출처를 상속하는 srcdoc 문서에 클릭을 위임한다. 라이브/스냅샷·30분 안전망 교체 시 새 문서에 다시 연결하고 이전 문서 리스너는 중단한다. 리포트·서버에 postMessage 코드나 새 API를 추가하지 않는다. `monitorbirthday.selfcheck.mjs`와 `scripts/verify_monitor_birthday.py`로 순서·드래그/터치·초기화 버튼·폴백/재로딩을 검사한다.
'''
assert needle in s;s=s.replace(needle,addition+needle)
save('docs/SPEC.md',s)
s=read('docs/TERMINOLOGY.md')
needle='| **사이트 기록 초기화**'
i=s.index(needle);z=s.index('\n',i)
s=s[:z]+'''\n| **모니터 생일 진입 명령** | 초기화 확인창 안에서 창 밖으로 ↑↑↓↓←→←→를 드래그·터치하고, 창이 닫힌 뒤 EXT → APP 탭으로 유노 생일 화면에 들어가는 숨은 입력. 각 방향을 인식한 가장자리가 빛나고 8방향 뒤 초기화 버튼이 빛난다. 기록을 지우지 않는다. |'''+s[z:]
save('docs/TERMINOLOGY.md',s)
s=read('docs/BIRTHDAY_SKIN.md')+'''
### 모니터에서 시험 화면 열기 (2026-11-01)

1. 운영 모니터에서 「사이트 기록 초기화」를 눌러 확인창을 연다.
2. 버튼을 제외한 창 안쪽에서 시작해 창 밖으로 ↑, ↑, ↓, ↓, ←, →, ←, → 순서로 한 번씩 드래그하거나 터치해 밀어낸다. 방향을 인식한 가장자리가 빛난다.
3. 초기화 버튼이 빛나고 확인창이 닫히면 리포트의 EXT 탭, APP 탭을 차례로 누른다. 유노 생일 인트로로 이동한다.

이 입력은 기록을 지우지 않는다. 되돌리기 버튼은 누르지 않는다. 틀린 탭이나 30초 무입력은 준비 상태를 취소한다. PC 마우스와 Android 터치 에뮬레이션으로 검사하며 실제 삼성 브라우저·iPhone은 운영자 확인 대상이다. 이 연결도 배포·푸시 전 상태다.
'''
save('docs/BIRTHDAY_SKIN.md',s)
s=read('docs/VERSION.md');needle='- 운영자가 후속 검증과 최종 번호를 확정한 뒤'
i=s.index(needle);s=s[:i]+'- 모니터 초기화 확인창의 방향 드래그/터치(↑↑↓↓←→←→)와 EXT→APP 탭으로 생일 화면에 진입하는 숨은 명령을 추가했다. 각 방향의 가장자리와 준비된 초기화 버튼이 빛난다. 저장값 삭제·백엔드 변경은 없으며 실제 삼성 브라우저 확인은 운영자 검증 대상이다.\n'+s[i:]
save('docs/VERSION.md',s)
m={}
for p in D.rglob('*'):
 if p.is_file():
  n=p.relative_to(D).as_posix();m[n]=hashlib.sha256((R/n).read_bytes()).hexdigest() if (R/n).exists() else None
(B/'monitor-manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8')
print('\n'.join(m))

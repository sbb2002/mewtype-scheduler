from pathlib import Path
import json,re,subprocess
B=Path(__file__).parent
R=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/docs-birthday-music-release')
status=json.loads((B/'release-status.json').read_text(encoding='utf8'));probe=json.loads((B/'release-probe.json').read_text(encoding='utf8'))
sha='6969df5871398a2daf12c02e82ee4fb453199db1'
deployment=next(d for d in status['deployments'] if d['sha']==sha)
assert deployment['state']=='READY';assert len(probe['files'])==8 and len(probe['media'])==2
def change(name,fn):
 p=R/name;p.write_text(fn(p.read_text(encoding='utf-8-sig')),encoding='utf8',newline='\n')
def version(s):
 marker='|---|---|---|---|---|---|\n'
 row=f"| v4.11.0 | `6969df5` | 2026-11-01 00:30 | `feat/birthday-music-scene` | 병합 커밋 | 프론트만 · 마이너 · PR #127 · Vercel 프로덕션 READY(`{deployment['id']}`) · 실기기 후속 확인 |\n"
 assert '| v4.11.0 |' not in s;s=s.replace(marker,marker+row,1)
 s=re.sub(r'  - \*\*배포 진행\*\*: 2026-11-01[^\n]*',f"  - **배포 완료(2026-11-01)**: 병합 `6969df5`(PR #127, 00:30 KST) → 주석 태그 `v4.11.0` → Vercel 프로덕션 READY(`{deployment['id']}`). 운영 버전·모니터/장면/음악 모듈 8개가 배포 소스와 일치하며 두 mp3 Range 응답 206을 확인했다. 롤백 = `fc6f8ca`(v4.10.0 배포 완료 main). 백엔드 변경 없음.",s)
 return s
change('docs/VERSION.md',version)
change('docs/BIRTHDAY_SKIN.md',lambda s:s.replace('v4.11.0, 2026-11-01 병합·배포 승인','v4.11.0, 2026-11-01 병합·배포 완료').replace('**출시 전 확인**','**배포 후 확인**').replace('2026-11-01 운영자 승인으로 v4.11.0 병합·배포를 진행한다. 실기기 확인은 운영자가 수행한다.', '2026-11-01 운영자 승인으로 v4.11.0 병합·프로덕션 배포를 완료했다(PR #127, `6969df5`). 실기기 확인은 운영자가 수행한다.').replace('이 연결도 v4.11.0에 포함해 운영자 승인으로 배포한다.', '이 연결도 v4.11.0 프로덕션 배포에 포함됐다.').replace('전체 출시 기준 통과로 처리하지 않는다.', '실기기 검증까지 모두 통과한 것으로 처리하지 않는다.'))
change('docs/BIRTHDAY_MUSIC_SCENE_VERIFICATION.md',lambda s:s.replace('2026-11-01 운영자가 병합·배포를 승인해 v4.11.0으로 진행한다.', '2026-11-01 운영자 승인으로 v4.11.0을 병합·프로덕션 배포했다(PR #127, `6969df5`).')+f'''
## 운영 반영 확인 (2026-11-01)

- 코드 병합: PR #127, `6969df5871398a2daf12c02e82ee4fb453199db1`. 주석 태그 `v4.11.0`도 같은 병합 커밋에 지정해 푸시했다.
- Vercel 프로덕션: `{deployment['id']}`, READY. 운영 주소 `https://mewtype-schduler.vercel.app/`에서 확인했다.
- `config.js` v4.11.0/2026-11-01, `monitor.html`, 방향 입력 두 모듈, 생일 장면·음악·플레이어·CSS를 포함한 8개 운영 파일이 배포 소스와 일치했다. 두 mp3 모두 첫 1024바이트가 원본과 일치하고 Range 206/전체 크기도 맞았다.
- 배포 후 상세 조작·실제 삼성 브라우저/iPhone 확인은 운영자가 모니터 페이지로 수행한다. 기존 실기기 미확인 표시는 유지한다. 롤백 기준은 `fc6f8ca`다.
''')
change('docs/BIRTHDAY_MUSIC_SCENE_HANDOFF.md',lambda s:s+f'''
## 7. 후속 완료 (2026-11-01)

위 미커밋·배포 금지 상태는 인계 당시 기록이다. 후속 구현·검증과 모니터 방향 입력/가장자리 표시를 완료했고, 2026-11-01 운영자 지시로 PR #127(`6969df5`)을 병합하고 v4.11.0을 프로덕션에 배포했다. 태그는 같은 코드 병합 커밋을 가리킨다. Vercel `{deployment['id']}` READY와 운영 파일 일치·음원 Range를 확인했다.

최신 근거는 `docs/BIRTHDAY_MUSIC_SCENE_VERIFICATION.md`와 `docs/VERSION.md`다. GPU 가속 CPU 8ms와 스테레오 무공백 검사는 통과했고 소프트웨어 렌더링은 8ms를 넘는다. 실제 삼성 브라우저·iPhone 확인은 운영자가 진행한다. 소스 버전 표기는 v4.11.0/2026-11-01로 갱신했다.
''')
body=f'''v4.11.0 코드 병합 `6969df5`(PR #127)와 같은 커밋의 주석 태그, Vercel 프로덕션 READY(`{deployment['id']}`)를 기록합니다.

운영 파일 8개가 배포 소스와 일치하고 두 mp3의 Range 206·크기·첫 1024바이트도 확인했습니다. 실기기 후속 검증은 운영자 확인 대상으로 유지합니다. 코드 변경은 없습니다.
'''
(B/'release-docs-pr-body.md').write_text(body,encoding='utf8')
print('배포 완료 표·태그·롤백·후속 확인 기록 갱신')

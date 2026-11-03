from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,subprocess,shutil
B=Path(__file__).parent;R=B.resolve().parents[1]
H=Path(r'C:/Users/User/AppData/Local/Temp/claude/C--Users-User-Documents-pyworks-mewtype-scheduler/cd557148-9ec6-47cb-b90f-a459b94aa233/scratchpad/handoff')
def git(*a):return subprocess.check_output(['git',*a],cwd=R,text=True,encoding='utf8').strip()
code='6969df5871398a2daf12c02e82ee4fb453199db1';main='2ee9cc70e86034cef8f041fa20d18f45889ecaa5'
assert git('branch','--show-current')=='main' and git('rev-parse','HEAD')==main and git('rev-parse','origin/main')==main
assert not git('status','--porcelain','--untracked-files=no')
assert git('rev-parse','refs/tags/v4.11.0^{}')==code
status=json.loads((B/'release-status.json').read_text(encoding='utf8'))
deploy=next(d for d in status['deployments'] if d['sha']==code);latest=next(d for d in status['deployments'] if d['sha']==main)
assert deploy['state']==latest['state']=='READY'
probe=json.loads((B/'release-probe.json').read_text(encoding='utf8'))
now=datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds')
data={'time_kst':now,'version':'v4.11.0','app_date':'2026-11-01','code_pr':127,'code_merge':code,'docs_pr':128,'main':main,'tag':'v4.11.0','tag_target':code,'code_deployment':deploy,'latest_deployment':latest,'runtime_probe':probe,'backend_deployed':False,'manual_device_testing':'운영자가 모니터 페이지에서 확인','worktrees_removed':['feat-birthday-music-scene','docs-birthday-music-release'],'preexisting_untracked_tools_preserved':True}
out=H/'verify/release';out.mkdir(parents=True,exist_ok=True)
(out/'release.json').write_text(json.dumps(data,sort_keys=True,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
for name in ['release-status.json','release-probe.json']:shutil.copyfile(B/name,out/name)
report=H/'REPORT.md'
with report.open('a',encoding='utf8') as f:f.write(f'''

## 병합·프로덕션 배포 완료 (2026-11-01)

운영자가 「이제 배포, 머지해줘. 나머지는 내가 모니터링 페이지를 통해 확인」이라고 승인해 이전 배포 보류를 해제했다. 새 요소 추가의 마이너 v4.11.0, APP_DATE 2026-11-01로 올려 PR #127을 병합했다.

- 코드 병합: `6969df5`(PR #127). 주석 태그 `v4.11.0`도 같은 병합 커밋을 가리키며 원격 푸시를 확인했다.
- 코드 프로덕션 배포: `{deploy['id']}`, READY.
- 배포 완료 문서: PR #128 병합 `2ee9cc7`. 현재 로컬/원격 main 일치.
- 문서 병합 후 최신 프로덕션 배포도 `{latest['id']}`, READY.
- 운영 주소 `https://mewtype-schduler.vercel.app/`에서 config v4.11.0과 모니터/방향 입력/생일 장면/음악/플레이어/CSS 8개 파일의 배포 소스 일치 확인. mp3 두 곡의 첫 1024바이트·전체 크기·Range 206 확인.
- README·CLAUDE 현재 버전, VERSION 태그 대조표·배포·롤백, 생일 검증/인수 문서를 갱신했다. 롤백 기준 `fc6f8ca`. 백엔드 배포 없음.
- 이번 작업의 두 워크트리만 병합·깨끗한 상태와 절대 경로를 확인한 뒤 정리했다. 다른 작업 워크트리와 기존 미추적 tools는 보존했다. 기존 문서 PR #122/#124는 병합하지 않았다.
- 실제 삼성/iPhone의 세부 동작은 운영자가 `[모니터](https://mewtype-schduler.vercel.app/monitor.html)`에서 확인한다. 초기화 확인창 안→밖으로 ↑↑↓↓←→←→, 버튼 빛/창 닫힘 뒤 EXT→APP이다. 상세 실기기 미확인 표시는 유지한다.

확인 시각 `{now}`. 배포 근거는 `verify/release/release.json` 및 원본 상태/HTTP 검사 JSON에 저장했다. 앞의 「푸시·배포 없음」은 당시 상태이며 현재는 위 프로덕션 배포 완료 상태다.
''')
(H/'DONE3.flag').write_text(f'구현·검증·보고·머지·프로덕션 배포 완료. v4.11.0 / main {main}. 실제 삼성/iPhone 확인은 운영자 진행.\n',encoding='utf8')
print(json.dumps({'version':'v4.11.0','main':main,'tag_target':code,'deployment':latest['state'],'monitor':'https://mewtype-schduler.vercel.app/monitor.html'},ensure_ascii=False))

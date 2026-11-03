from pathlib import Path
import json,os,requests
root=Path(__file__).resolve().parents[2]
files=['js/config.js','css/birthday.css','css/bdayplayer.css','js/bdayaudio.js','js/bdayplayerdrag.js','js/bdayscene-yuno.js','js/bdaystars.js','js/musicpriority.js','js/player.js']
for name in files:
 r=requests.get('https://mewtype-schduler.vercel.app/'+name,params={'release_check':'ba2b65b'},timeout=30);r.raise_for_status()
 assert r.content.decode('utf8').replace('\r\n','\n')==(root/'src/frontend'/name).read_text(encoding='utf8'),name
out=Path(os.environ['TEMP'])/'birthday-greeting-motion/release.json'
out.write_text(json.dumps({'version':'v4.11.2','merge':'ba2b65b10d83c0db319f288b64c1bdd5540b3496','deployment':'dpl_4JTKp22MjRpckyTmzU1S7pxysFqz','production_files_match':files},sort_keys=True,indent=2)+'\n',encoding='utf8')
print('Production files match: 9; version v4.11.2')
docs=root.parent/'mewtype-scheduler-worktrees/v4/docs-birthday-greeting-release/docs'
p=docs/'VERSION.md';s=p.read_text(encoding='utf8')
s=s.replace('| v4.11.1 |','| v4.11.2 | `ba2b65b` | 2026-11-01 01:30 | `hotfix/birthday-greeting-motion` | 병합 커밋 | 프론트만 · 운영자 지정 핫픽스 · PR #131 · Vercel READY(`dpl_4JTKp22MjRpckyTmzU1S7pxysFqz`) |\n| v4.11.1 |',1)
s=s.replace('배포 진행: 검증 후 병합·배포.','배포 완료: PR #131 병합 `ba2b65b`, 태그 `v4.11.2` 원격 게시. Vercel `dpl_4JTKp22MjRpckyTmzU1S7pxysFqz` READY. 운영 도메인의 변경 파일 9개가 병합 코드와 일치하고 버전 v4.11.2를 확인했다.',1)
p.write_text(s,encoding='utf8')
p=docs/'BIRTHDAY_GREETING_HOTFIX_VERIFICATION.md';s=p.read_text(encoding='utf8').replace('검증 후 배포 진행. 롤백 대상은 v4.11.1 완료 main `d77667b`이며 병합·태그·Vercel 식별자는 완료 후 기록한다.','PR #131 병합 `ba2b65b`에 태그 `v4.11.2`를 게시했다. Vercel 프로덕션 `dpl_4JTKp22MjRpckyTmzU1S7pxysFqz` READY 및 운영 도메인 변경 파일 9개 일치·버전 v4.11.2를 확인했다. 롤백 대상은 v4.11.1 완료 main `d77667b`다. 배포 증거는 같은 임시 폴더의 release.json에 저장했다.');p.write_text(s,encoding='utf8')

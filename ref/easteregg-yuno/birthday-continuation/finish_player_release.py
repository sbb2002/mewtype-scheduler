from pathlib import Path
import json, os, requests

root = Path(__file__).resolve().parents[2]
files = ['js/config.js', 'monitor.html', 'js/monitorbirthday.js', 'js/monitorbirthdaylogic.js', 'js/bdayplayerdrag.js', 'js/bdayplayer.js', 'css/bdayplayer.css', 'css/birthday.css']
for name in files:
    response = requests.get('https://mewtype-schduler.vercel.app/' + name, params={'release_check': '779842c'}, timeout=30)
    response.raise_for_status()
    assert response.content.decode('utf8').replace('\r\n', '\n') == (root/'src/frontend'/name).read_text(encoding='utf8'), name
assert "4.11.1" in (root/'src/frontend/js/config.js').read_text(encoding='utf8')
out = Path(os.environ['TEMP'])/'birthday-player-ui/release.json'
out.write_text(json.dumps({'version':'v4.11.1','merge':'779842c65ee326fa00e7f411f3f8c3acee50d16b','deployment':'dpl_9cVxEymqjH2jGCfFtm8T2HMPbrKv','production_files_match':files},sort_keys=True,indent=2)+'\n',encoding='utf8')
print('Production files match: 8; version v4.11.1')
docs = root.parent/'mewtype-scheduler-worktrees/v4/docs-birthday-player-release/docs'
p = docs/'VERSION.md'
s = p.read_text(encoding='utf8')
s = s.replace('| v4.11.0 |', '| v4.11.1 | `779842c` | 2026-11-01 01:09 | `hotfix/birthday-player-controls` | 병합 커밋 | 프론트만 · 운영자 지정 핫픽스 · PR #129 · Vercel READY(`dpl_9cVxEymqjH2jGCfFtm8T2HMPbrKv`) |\n| v4.11.0 |', 1)
s = s.replace('**배포 진행**: 사용자 승인으로 검증 후 병합·프로덕션 배포한다. 완료 뒤 병합 커밋·태그·Vercel 식별자를 기록한다.', '**배포 완료**: PR #129 병합 `779842c`, 태그 `v4.11.1` 원격 게시. Vercel 프로덕션 `dpl_9cVxEymqjH2jGCfFtm8T2HMPbrKv` READY. 운영 도메인의 변경 파일 8개가 병합 코드와 일치하고 config.js v4.11.1을 확인했다.')
p.write_text(s,encoding='utf8')
p = docs/'BIRTHDAY_PLAYER_HOTFIX_VERIFICATION.md'
s = p.read_text(encoding='utf8')
s += '\n## 배포 확인\n\nPR #129 병합 `779842c`에 태그 `v4.11.1`을 게시했다. Vercel 프로덕션 `dpl_9cVxEymqjH2jGCfFtm8T2HMPbrKv` READY 및 운영 도메인 변경 파일 8개 일치·버전 v4.11.1을 확인했다. 롤백 대상은 `2ee9cc7`이다. 배포 증거는 같은 임시 폴더의 release.json에 저장했다.\n'
p.write_text(s,encoding='utf8')
p = docs/'BIRTHDAY_SKIN.md'
s = p.read_text(encoding='utf8').replace('이 연결도 v4.11.0 프로덕션 배포에 포함됐다.', '기본 연결은 v4.11.0에, A/B 안내와 모바일 안쪽 스와이프 보완은 v4.11.1 프로덕션 배포에 포함됐다.')
p.write_text(s,encoding='utf8')

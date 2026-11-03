from pathlib import Path
import json,subprocess
B=Path(__file__).parent;R=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
def git(*a):return subprocess.check_output(['git',*a],cwd=R,text=True,encoding='utf8').strip()
assert git('branch','--show-current')=='feat/birthday-music-scene'
assert not git('diff','--cached','--name-only'),'다른 스테이징이 있어 중단'
assert not git('diff','--name-only','--','src/frontend/js/config.js')
paths=['src/frontend/monitor.html','src/frontend/js/monitorbirthday.js','src/frontend/js/monitorbirthdaylogic.js','src/frontend/js/monitorbirthday.selfcheck.mjs','scripts/verify_monitor_birthday.py','docs/SPEC.md','docs/TERMINOLOGY.md','docs/BIRTHDAY_SKIN.md','docs/VERSION.md','docs/BIRTHDAY_MUSIC_SCENE_VERIFICATION.md']
git('add','--',*paths);git('diff','--cached','--check')
subject='모니터 팝업의 방향 입력과 탭 명령으로 생일 화면 연결'
git('commit','-m',subject,'-m','방향을 인식한 가장자리와 준비된 초기화 버튼을 밝히고, EXT→APP으로 유노 인트로에 진입한다. 마우스·Android 터치, 저장값 보존과 정상 초기화를 검증했다.','-m','Co-Authored-By: Codex <noreply@openai.com>')
result={'commit':git('rev-parse','HEAD'),'subject':subject}
(B/'monitor-commit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False))

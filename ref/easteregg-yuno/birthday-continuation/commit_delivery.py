from pathlib import Path
import subprocess,json
ROOT=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True,encoding='utf8').strip()
assert git('branch','--show-current')=='feat/birthday-music-scene'
staged=git('diff','--cached','--name-only').splitlines()
git('diff','--check')
assert not git('diff','--name-only','--','src/frontend/js/config.js'),'버전 상수 변경이 있어 중단'
groups=[
 ('유노 생일 화면에 음악 연동 장면과 일출·조명 인트로 추가',[
 'src/frontend/index.html','src/frontend/js/bdayscene-yuno.js','src/frontend/js/bdayscene-yuno.selfcheck.mjs','src/frontend/js/birthdayui.js','src/frontend/js/bdayaudio.js','src/frontend/js/bdayguard.js','src/frontend/js/bdaylogic.js','src/frontend/js/bdaymusic.selfcheck.mjs','src/frontend/js/bdayplayer.js','src/frontend/js/bdaysign.js','src/frontend/css/bdayplayer.css','src/frontend/assets/birthday/beat','src/frontend/assets/birthday/bgm','src/frontend/assets/birthday/ufo.png']),
 ('생일 음악 장면의 픽셀·수명·성능·무공백 재생 검증 추가',[
 'fixtures/bdayscene-yuno.html','fixtures/validate-bdayscene-yuno.cjs','scripts/compare_birthday_pixels.py','scripts/port_birthday_scene.py','scripts/verify_birthday_addendum.py','scripts/verify_birthday_gapless.py','scripts/verify_birthday_lifecycle.py','scripts/verify_birthday_music.py','scripts/verify_birthday_performance.py']),
 ('생일 음악 장면 구현과 3차 검증 결과·미확인 사항 문서화',[
 'CLAUDE.md','docs/BIRTHDAY_SKIN.md','docs/SPEC.md','docs/VERSION.md','docs/BIRTHDAY_MUSIC_SCENE_VERIFICATION.md'])]
out=[]
assert all(any(n==p or n.startswith(p+'/') for p in groups[0][1]) for n in staged),'이번 작업 밖의 스테이징이 있어 중단'
for subject,paths in groups:
 git('add','--',*paths)
 git('diff','--cached','--check')
 git('commit','-m',subject,'-m','Co-Authored-By: Codex <noreply@openai.com>')
 out.append({'commit':git('rev-parse','HEAD'),'subject':subject})
Path(__file__).with_name('commits.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(out,ensure_ascii=False,indent=2))

from pathlib import Path
import hashlib,json
BASE=Path(__file__).parent;D=BASE/'delivery';ROOT=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
p=D/'src/frontend/js/bdayaudio.js';s=p.read_text(encoding='utf8').replace("buffers?.[i].duration||audios[i].duration||0", "buffers?.[i].duration||(Number.isFinite(audios[i].duration)?audios[i].duration:Infinity)")
s=s.replace("engine:bufferMode?'buffer':'stream',scheduled:", "engine:bufferMode?'buffer':'stream',decoded:!!buffers,scheduled:")
p.write_text(s,encoding='utf8',newline='\n')
p=D/'scripts/verify_birthday_lifecycle.py';s=p.read_text(encoding='utf8').replace("page.wait_for_timeout(2200)", "page.wait_for_function('!document.documentElement.hasAttribute(\"data-bday-intro\")')")
s=s.replace("page.wait_for_function('__birthday.audio.diagnostics().engine===\"buffer\"')", "page.wait_for_function('__birthday.audio.diagnostics().decoded')")
p.write_text(s,encoding='utf8',newline='\n')
s=(ROOT/'scripts/verify_birthday_music.py').read_text(encoding='utf8')
s=s.replace("    page.evaluate('()=>__birthday.audio.audio.dispatchEvent(new Event(\"ended\"))');page.wait_for_timeout(600)", "    page.evaluate('async()=>{await __birthday.audio.seek(__birthday.audio.audio.duration-.25);await __birthday.audio.play()}');page.wait_for_function('__birthday.audio.index===0')")
s=s.replace("results['ended']", "results['natural_boundary']")
p=D/'scripts/verify_birthday_music.py';p.write_text(s,encoding='utf8',newline='\n')
manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf8'))
for p in D.rglob('*'):
 if p.is_file():
  name=p.relative_to(D).as_posix();target=ROOT/name;manifest[name]=hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
(BASE/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')

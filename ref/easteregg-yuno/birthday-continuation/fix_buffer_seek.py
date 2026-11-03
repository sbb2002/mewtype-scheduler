from pathlib import Path
import json,hashlib
B=Path(__file__).parent;D=B/'delivery';R=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
p=D/'src/frontend/js/bdayaudio.js';s=p.read_text(encoding='utf8')
s=s.replace('const rev=++revision,i=index;await preload(i);if(dead||rev!==revision)return;', 'const rev=++revision,i=index;await preload(i);if(warming)await warming;if(dead||rev!==revision)return;')
s=s.replace('(Number.isFinite(audios[i].duration)?audios[i].duration:Infinity)', '(audios[i].duration>0&&Number.isFinite(audios[i].duration)?audios[i].duration:Infinity)')
s=s.replace('    state.value=null;if(bufferMode){position=target;if(playing)startBuffers(target)}else audios[i].currentTime=target;', '''    state.value=null;
    if(buffers&&!bufferMode){playing=!audios[i].paused;bufferMode=true;audios[i].pause()}
    if(bufferMode){position=target;if(playing)startBuffers(target);else stopNodes()}else audios[i].currentTime=target;
    emit();''')
p.write_text(s,encoding='utf8',newline='\n')
m=json.loads((B/'manifest.json').read_text(encoding='utf8'))
for n in m:m[n]=hashlib.sha256((R/n).read_bytes()).hexdigest() if (R/n).exists() else None
(B/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8')

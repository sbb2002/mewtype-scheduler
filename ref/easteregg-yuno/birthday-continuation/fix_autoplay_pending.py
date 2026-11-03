from pathlib import Path
import json,hashlib
B=Path(__file__).parent;D=B/'delivery';R=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
p=D/'src/frontend/js/bdayaudio.js';s=p.read_text(encoding='utf8')
s=s.replace('queue=[],handover=0,poll=0;', 'queue=[],handover=0,poll=0,autoplayTimer=0;')
s=s.replace('    await audios[index].play();', '''    const media=audios[index],attempt=media.play();resume?.catch(()=>{});
    // 停止中の AudioContext に接続すると play 自体が未解決になるブラウザもある。
    if(context?.state==='suspended'){
      try{await Promise.race([attempt,new Promise((resolve,reject)=>{autoplayTimer=setTimeout(()=>{
        autoplayTimer=0;if(dead||rev!==playRevision)return resolve();
        if(context?.state==='suspended'){media.pause();reject(new DOMException('사용자 조작이 필요합니다','NotAllowedError'))}else resolve(attempt);
      },250)})])}finally{clearTimeout(autoplayTimer);autoplayTimer=0}
    }else await attempt;''')
s=s.replace('// 停止中の AudioContext に接続すると play 自体が未解決になるブラウザもある。','// 정지된 AudioContext에서는 play 요청도 대기하는 브라우저가 있어 탭 안내로 전환한다.')
s=s.replace('playing=false;stopNodes();abort.abort();', 'playing=false;clearTimeout(autoplayTimer);autoplayTimer=0;stopNodes();abort.abort();')
s=s.replace('handover:!!handover}', 'handover:!!handover,autoplayTimer:!!autoplayTimer}')
p.write_text(s,encoding='utf8',newline='\n')
m=json.loads((B/'manifest.json').read_text(encoding='utf8'))
for n in m:m[n]=hashlib.sha256((R/n).read_bytes()).hexdigest() if (R/n).exists() else None
(B/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8')

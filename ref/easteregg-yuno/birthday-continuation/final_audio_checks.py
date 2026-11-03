from pathlib import Path
import json,hashlib
B=Path(__file__).parent;D=B/'delivery';R=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
p=D/'src/frontend/js/bdayaudio.js';s=p.read_text(encoding='utf8')
s=s.replace('  async function preload(i){', '''  // blob 교체 뒤 메타데이터가 준비되기 전에 탐색하면 브라우저가 시각을 0으로 되돌릴 수 있다.
  function metadata(a){return new Promise((resolve,reject)=>{
    const cleanup=()=>{a.removeEventListener('loadedmetadata',ready);a.removeEventListener('error',fail);abort.signal.removeEventListener('abort',fail)};
    const ready=()=>{cleanup();resolve()},fail=()=>{cleanup();reject(abort.signal.reason||new Error('음원 메타데이터 로드 실패'))};
    if(abort.signal.aborted||a.error)return fail();if(a.readyState>=1)return ready();
    a.addEventListener('loadedmetadata',ready);a.addEventListener('error',fail);abort.signal.addEventListener('abort',fail,{once:true});
  })}
  async function preload(i){''')
s=s.replace("}).then(b=>{if(dead)return;", "}).then(async b=>{if(dead)return;")
s=s.replace('audios[i].src=u;if(t)', 'audios[i].src=u;await metadata(audios[i]);if(dead)return;if(t)')
p.write_text(s,encoding='utf8',newline='\n')
p=D/'scripts/verify_birthday_lifecycle.py';s=p.read_text(encoding='utf8')
s=s.replace("    page.goto('http://127.0.0.1:8102/src/frontend/');page.wait_for_timeout(1500)\n    result['ordinary_baseline']=page.evaluate('()=>audit()')\n", '')
s=s.replace("    result['errors']=errors", "    page.goto('http://127.0.0.1:8102/src/frontend/');page.wait_for_timeout(1000)\n    result['ordinary_baseline']=page.evaluate('()=>audit()')\n    result['errors']=errors")
s=s.replace("    page.goto('http://127.0.0.1:8102/src/frontend/?bday=yuno&ufo=sign');page.wait_for_timeout(2000)", "    page.goto('http://127.0.0.1:8102/src/frontend/?bday=yuno&ufo=sign');page.locator('.bday-start').wait_for(state='visible');page.wait_for_timeout(200)")
p.write_text(s,encoding='utf8',newline='\n')
m=json.loads((B/'manifest.json').read_text(encoding='utf8'))
for n in m:m[n]=hashlib.sha256((R/n).read_bytes()).hexdigest() if (R/n).exists() else None
(B/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8')

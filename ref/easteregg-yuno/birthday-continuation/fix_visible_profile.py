from pathlib import Path
import json,hashlib
B=Path(__file__).parent;D=B/'delivery';R=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
p=D/'src/frontend/js/bdayscene-yuno.js';s=p.read_text(encoding='utf8')
s=s.replace("  lightLayer.style.display='none';frontLayer.style.display=effect.spot?'block':'none';", "  const waveActive=introActive()&&!still&&t>=17.14&&t<17.64;\n  lightLayer.style.display=waveActive?'block':'none';frontLayer.style.display=effect.spot?'block':'none';")
s=s.replace("lightLayer.style.filter=`brightness(${introBrightness(t)})`;lightLayer.style.display='block';", "lightLayer.style.filter=`brightness(${introBrightness(t)})`;")
p.write_text(s,encoding='utf8',newline='\n')
p=D/'scripts/verify_birthday_performance.py';s=p.read_text(encoding='utf8')
s=s.replace("s=(ROOT/'src/frontend/js/bdayscene-yuno.js').read_text(encoding='utf8')", "s=(ROOT/'src/frontend/js/bdayscene-yuno.js').read_text(encoding='utf8').replace('return {whenReady,setBrightness', 'return {stopForTest(){cancelAnimationFrame(raf);raf=0},whenReady,setBrightness')")
s=s.replace("page.evaluate('()=>{__birthday.audio.pause();document.querySelector(\"#bday-bg\").style.transform=\"translateX(300vw)\"}')", "page.evaluate('()=>{__birthday.audio.pause();__birthday.scene.stopForTest()}')")
s=s.replace(" result['renderer']=", " result['browser_version']=browser.version\n result['method']='visible canvas; test-only RAF cancellation; 120 draws with RAF pacing'\n result['gpu_features']=browser.new_browser_cdp_session().send('SystemInfo.getInfo')['gpu']['featureStatus']\n result['renderer']=")
s=s.replace('return {mean:a.reduce', 'return {samples:a.length,max:Math.max(...a),mean:a.reduce')
p.write_text(s,encoding='utf8',newline='\n')
m=json.loads((B/'manifest.json').read_text(encoding='utf8'))
for n in m:m[n]=hashlib.sha256((R/n).read_bytes()).hexdigest() if (R/n).exists() else None
(B/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8')

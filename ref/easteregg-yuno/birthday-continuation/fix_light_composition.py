from pathlib import Path
import json,hashlib
B=Path(__file__).parent;D=B/'delivery';R=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
p=D/'src/frontend/js/bdayscene-yuno.js';s=p.read_text(encoding='utf8')
needle=" const lightLayer=document.createElement('canvas'),frontLayer=document.createElement('canvas'),spotLayer=document.createElement('canvas');let spotCacheKey=null;"
s=s.replace(needle,needle+'''
 // 밝기 증폭 뒤 부모에서 다시 감쇠하면 8비트 색이 먼저 클리핑된다. 레이어별 최종 밝기를 합성한다.
 for(const layer of [frontLayer,lightLayer]){layer.draggable=false;layer.style.cssText='position:absolute;left:0;top:0;pointer-events:none;display:none';host.append(layer)}
 lightLayer.style.width=lightLayer.style.height='100%';
 function setBrightness(value){canvas.style.filter=`brightness(${value})`;frontLayer.style.filter=`brightness(${value*(1+effect.spot*1.85)})`}
''')
s=s.replace('  bg(c);', "  setBrightness(introActive()?(t>=17.14&&t<17.64&&!still?.3:introBrightness(t,still)):1);\n  lightLayer.style.display='none';frontLayer.style.display=effect.spot?'block':'none';\n  bg(c);")
s=s.replace("   c.save();c.setTransform(1,0,0,1,0,0);c.filter=`brightness(${1+effect.spot*1.85})`;c.drawImage(frontLayer,ox+380*s,oy+160*s);c.restore();", "   frontLayer.style.left=`${(ox+380*s)/d}px`;frontLayer.style.top=`${(oy+160*s)/d}px`;frontLayer.style.width=`${fw/d}px`;frontLayer.style.height=`${fh/d}px`;")
s=s.replace("lc.clearRect(0,0,w,h);lc.filter=`brightness(${introBrightness(t)/.3})`;", "lc.clearRect(0,0,w,h);")
s=s.replace("if(right>left&&bottom>top)lc.drawImage(canvas,left,top,right-left,bottom-top,left,top,right-left,bottom-top);lc.filter='none';", "if(right>left&&bottom>top)lc.drawImage(canvas,left,top,right-left,bottom-top,left,top,right-left,bottom-top);\n   if(effect.spot)lc.drawImage(frontLayer,ox+380*s,oy+160*s);")
s=s.replace("lc.globalCompositeOperation='source-over';c.save();c.setTransform(1,0,0,1,0,0);c.drawImage(copy,0,0);c.restore();", "lc.globalCompositeOperation='source-over';lightLayer.style.filter=`brightness(${introBrightness(t)})`;lightLayer.style.display='block';")
s=s.replace('return {whenReady,setIntro(fn)', 'return {whenReady,setBrightness,setIntro(fn)')
s=s.replace('canvas.remove();spotLayer.width', 'canvas.remove();frontLayer.remove();lightLayer.remove();spotLayer.width')
p.write_text(s,encoding='utf8',newline='\n')
p=D/'src/frontend/js/bdayplayer.js';s=(R/'src/frontend/js/bdayplayer.js').read_text(encoding='utf8')
s=s.replace('host.style.filter=`brightness(${(!reduced()&&t>=17.14&&t<17.64?.3:introBrightness(t,reduced()))})`;', 'scene.setBrightness(!reduced()&&t>=17.14&&t<17.64?.3:introBrightness(t,reduced()));')
p.write_text(s,encoding='utf8',newline='\n')
for name in ['scripts/verify_birthday_music.py','scripts/verify_birthday_lifecycle.py','scripts/verify_birthday_addendum.py']:
 p=D/name;s=p.read_text(encoding='utf8') if p.exists() else (R/name).read_text(encoding='utf8')
 s=s.replace('getComputedStyle(document.querySelector("#bday-bg")).filter', 'getComputedStyle(document.querySelector("#bday-bg canvas")).filter')
 s=s.replace("page.locator('#bday-bg').evaluate('(e)=>getComputedStyle(e).filter')", "page.locator('#bday-bg canvas').first.evaluate('(e)=>getComputedStyle(e).filter')")
 s=s.replace('document.querySelector("#bday-bg").style.filter=`brightness(${t>=17.14&&t<17.64?.3:m.introBrightness(t)})`', '__birthday.scene.setBrightness(t>=17.14&&t<17.64?.3:m.introBrightness(t))')
 p.write_text(s,encoding='utf8',newline='\n')
p=D/'docs/SPEC.md';s=p.read_text(encoding='utf8').replace('setLayout, setIntro }','setLayout, setIntro, setBrightness }')
s=s.replace('캐릭터/파면 필터 영역 제한으로', '캐릭터/파면의 CSS 합성 레이어 분리로')
s=s.replace('첫 드럼 17.14초에 태양에서', '기본 장면·유노 조명·점등 전파는 별도 Canvas의 최종 CSS 밝기로 합성한다. 부모에서 다시 감쇠해 색이 회색으로 클리핑되는 중간 합성을 피한다. 첫 드럼 17.14초에 태양에서')
p.write_text(s,encoding='utf8',newline='\n')
m=json.loads((B/'manifest.json').read_text(encoding='utf8'))
for p in D.rglob('*'):
 if p.is_file():
  n=p.relative_to(D).as_posix();m[n]=hashlib.sha256((R/n).read_bytes()).hexdigest() if (R/n).exists() else None
(B/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8')

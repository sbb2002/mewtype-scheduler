"""승인된 v12의 Canvas 수식을 앱 모듈로 이식하는 재현 스크립트."""
from pathlib import Path
import json, re, base64, shutil

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = Path(r'C:\Users\User\AppData\Local\Temp\claude\C--Users-User-Documents-pyworks-mewtype-scheduler\cd557148-9ec6-47cb-b90f-a459b94aa233\scratchpad\handoff')
src = (HANDOFF / 'prototype_v12.html').read_text(encoding='utf-8')
s = src[src.index('const spectrumHash19'):]
data = json.loads(re.search(r'const SKY_SIGN_DATA=(.*?);', s).group(1))
widths = json.loads(re.search(r'const SKY_SIGN_WIDTHS=(.*?);', s).group(1))
encoded = base64.b64encode(json.dumps([data, widths], separators=(',', ':')).encode()).decode()
sign = "// 유노 사인 좌표: 우연한 복사를 줄이는 인코딩이며 보안 암호화가 아니다.\nconst DATA='" + encoded + "';\nexport function decodeSign(){ return JSON.parse(atob(DATA)); }\n"
(ROOT / 'src/frontend/js/bdaysign.js').write_text(sign, encoding='utf-8')
# DOM 시안 껍데기와 오디오 데모를 제외하고 함수 본문을 보존한다.
body = s[:s.index('const TRACKS=')] + s[s.index('function line('):s.index('function seekAudio(')]
body = re.sub(r'const SKY_SIGN_DATA=.*?;\nconst SKY_SIGN_WIDTHS=.*?;', 'const [SKY_SIGN_DATA,SKY_SIGN_WIDTHS]=decodeSign();', body)
body = body.replace("i.src='yuno/'+n+'.webp'", "i.src=new URL('../assets/birthday/yuno/'+n+'.webp',import.meta.url).href")
body = body.replace("skyUFO.src='ufo.png'", "skyUFO.src=new URL('../assets/birthday/ufo.png',import.meta.url).href")
body = body.replace('window.fxSnapshot7=', 'snapshot=')
body = re.sub(r'window.wavePositions=.*?;\n', '', body)
# 첫 드럼의 초 시각과 박 도메인을 모두 교정한다.
body = body.replace('drop:midnight?24:32', 'drop:midnight?24:beatPos(17.14)')
body = body.replace('drop:B[drop]', 'drop:mid?B[drop]:17.14')
body = body.replace('birth:B[drop]-6', 'birth:(mid?B[drop]:17.14)-6')
body = body.replace("c.save();c.beginPath();c.arc(850,267,102", "c.save();sunTransform(c);c.beginPath();c.arc(850,267,102")
body = body.replace("const cx=850,cy=267,segment=", "sunTransform(c);const cx=850,cy=267,segment=")
# 유노와 데크를 함께 이동하므로 손 접촉 계산의 내부 좌표는 원본을 유지한다.
body = body.replace('const skySignDraw', 'const skySignDraw')
body = body.replace('function skySignDraw(c,f,age){', 'function skySignDraw(c,f,age){\n c.save();c.translate(55,30);c.scale(.88,.88);c.translate(-55,-30);skySignDrawOriginal(c,f,age);c.restore();\n}\nfunction skySignDrawOriginal(c,f,age){')
# 사인 합성과 디코더를 별도 모듈로 분리한다.
sign_start=body.index('const skySign=')
sign_end=body.index('const skyPlans=')
sign_functions=body[sign_start:sign_end]
sign += '\nexport function createSkySign({djClamp15,djEase15,skyStar,skyUFO}){\nconst [SKY_SIGN_DATA,SKY_SIGN_WIDTHS]=decodeSign();\n'+sign_functions+'\nreturn {skySign,skySignPos,skySignDraw};\n}\n'
(ROOT / 'src/frontend/js/bdaysign.js').write_text(sign,encoding='utf8')
body=body[:sign_start]+'const {skySign,skySignPos,skySignDraw}=createSkySign({djClamp15,djEase15,skyStar,skyUFO});\n'+body[sign_end:]
body=body.replace('const [SKY_SIGN_DATA,SKY_SIGN_WIDTHS]=decodeSign();','')
body=body.replace('if(age>=0&&age<1.6){','if(!introActive()&&age>=0&&age<1.6){')
# 세로 화면에서 기존 원근 수식을 760 아래까지 이어 그린다(기존 범위 수식은 보존).
floor_start=body.index('function floorWave(')
floor=body[floor_start:]
floor=floor.replace("c.rect(0,395,1200,365)","c.rect(0,395,1200,groundBottom-395)")
floor=floor.replace("c.fillRect(0,395,1200,365)","c.fillRect(0,395,1200,groundBottom-395)")
floor=floor.replace('height:760','height:Math.ceil(groundBottom)')
floor=floor.replace('clearRect(0,0,1200,760)','clearRect(0,0,1200,groundBottom)')
floor=floor.replace('j<=N+1','j<=N*Math.pow((groundBottom-395)/365,.4)+2')
floor=floor.replace('z>1','yBeyond(z)')
floor=floor.replace('const N=12,', 'const yBeyond=z=>395+365*z**2.5>groundBottom;const N=12,')
floor=floor.replace('const gr=ctx.createLinearGradient(600,389,x,760);', 'const ex=600+(x-600)*(groundBottom-389)/371;const gr=ctx.createLinearGradient(600,389,ex,groundBottom);')
floor=floor.replace('ctx.lineTo(x,760)','ctx.lineTo(ex,groundBottom)')
floor=floor.replace('y0>759','y0>groundBottom-1').replace('Math.min(760,y1)','Math.min(groundBottom,y1)')
floor=floor.replace('fillRect(0,0,1200,760)','fillRect(0,0,1200,groundBottom)')
# 회전·주소창 변화 후에도 작업 버퍼를 화면 아래까지 맞춘다.
floor=floor.replace("const mk=k=>FL[k]||(FL[k]=Object.assign(document.createElement('canvas'),{width:1200,height:Math.ceil(groundBottom)}));", "const mk=k=>{const cv=FL[k]||(FL[k]=document.createElement('canvas')),h=Math.ceil(groundBottom);if(cv.width!==1200||cv.height!==h){cv.width=1200;cv.height=h}return cv};")
body=body[:floor_start]+floor
header = "// 정본 prototype_v12.html에서 수식·상수를 이식. 카메라/드롭/사인 폭만 정본 명세대로 변경.\nimport { createSkySign } from './bdaysign.js';\nimport { sceneLayout } from './bdaylogic.js';\nexport function mountYunoScene(host,opts={}) {\nlet snapshot=null,activeLayout=null,introActive=()=>false,groundBottom=760;\nfunction sunTransform(c){if(activeLayout?.portrait){c.translate(775,267);c.scale(activeLayout.sunScale,activeLayout.sunScale);c.translate(-850,-267)}}\n"
footer = """
 const canvas=document.createElement('canvas');canvas.draggable=false;canvas.style.cssText='width:100%;height:100%;display:block';host.append(canvas);
 const c=canvas.getContext('2d');let clock=()=>0,still=false,dead=false,raf=0,visible=true,layout=null,lastT=null,parts=[],lastFrame=0;
 const costs=[];
 const images=[...Object.values(YN),skyUFO];
 const whenReady=Promise.all(images.map(i=>i.decode()));
 function draw(t=clock()) {
  if(dead||!TRK)return;
  const start=performance.now(),r=host.getBoundingClientRect(),d=Math.min(devicePixelRatio||1,1.5),w=Math.round(r.width*d),h=Math.round(r.height*d);
  if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h}
  const L=layout||sceneLayout(r.width,r.height),s=L.scale*d,ox=w/2-600*s,oy=L.offsetY*d;activeLayout=L;groundBottom=L.portrait?Math.max(760,(h-oy)/s):760;
  c.setTransform(1,0,0,1,0,0);c.fillStyle='#170725';c.fillRect(0,0,w,h);
  c.setTransform(s,0,0,s,ox,oy);
  // 세로 하늘은 원래 그라데이션의 시작색으로 이어지고 바닥은 아래까지 연장된다.
  if(L.portrait){c.fillStyle='#110e20';c.fillRect(-2000,395,5200,4000);for(let i=0;i<55;i++){c.fillStyle='rgba(138,227,226,.22)';c.fillRect(220+(i*173)%820,-900+(i*71)%900,1.7,1.7)}}
  bg(c);
  skyProps(c,t);floorWave(c,0,t);visual(c,5,t);
  if(introActive()&&!still&&t>=17.14&&t<17.69){const u=(t-17.14)/.55;c.save();sunTransform(c);for(let j=0;j<3;j++){c.strokeStyle=[P,V,C][j];c.globalAlpha=(1-u)*.9;c.lineWidth=7-j;c.beginPath();c.arc(850,267,100+500*u-j*18,0,Math.PI*2);c.stroke()}c.restore()}
  c.save();if(L.portrait){const k=L.signWidth/440;c.translate(600-k*275,L.signY);c.scale(k,k)}skyUfos(c,t);c.restore();
  c.save();c.translate(-75,0);front(c,t);c.restore();
  // 기존 🎂 전환 폭죽의 수식·색·지연을 유지한다. 음악 장면 자체와는 별도이며 인트로에는 호출하지 않는다.
  const now=performance.now(),dt=lastFrame?Math.min(.05,(now-lastFrame)/1000):0;lastFrame=now;
  if(parts.length){c.save();c.setTransform(d,0,0,d,0,0);for(const p of parts){p.age+=dt;if(p.age<p.delay)continue;const age=p.age-p.delay;p.x+=p.vx*dt;p.y+=p.vy*dt;p.vy+=20*dt;p.vx*=Math.exp(-dt*.35);c.globalAlpha=Math.max(0,1-age/(p.life||2.1))*.85;c.fillStyle=p.color;c.beginPath();c.arc(p.x,p.y,p.r,0,Math.PI*2);c.fill()}parts=parts.filter(p=>p.age-p.delay<(p.life||2.1));c.restore()}
  costs.push(performance.now()-start);if(costs.length>300)costs.shift();lastT=t;
 }
 function frame(){raf=0;if(dead)return;if(!document.hidden&&visible&&(!still||lastT===null)){const t=still?0:clock();if(t!==lastT||parts.length)draw(t)}if(!still&&!document.hidden&&visible)raf=requestAnimationFrame(frame)}
 function resume(){if(!dead&&!raf&&!document.hidden&&visible)raf=requestAnimationFrame(frame)}
 function visibility(){if(document.hidden){cancelAnimationFrame(raf);raf=0}else resume()}
 function resize(){layout=null;lastT=null;draw(still?0:clock());resume()}
 const observer=new IntersectionObserver(es=>{visible=es[0].isIntersecting;if(!visible){cancelAnimationFrame(raf);raf=0}else resume()});observer.observe(canvas);
 document.addEventListener('visibilitychange',visibility);window.addEventListener('resize',resize);window.visualViewport?.addEventListener('resize',resize);
 whenReady.then(()=>{if(!dead){draw(0);resume()}}).catch(()=>{});
 return {whenReady,setIntro(fn){introActive=fn},setClock(fn){clock=fn;lastT=null;resume()},setTrack(track){TRK=track;lastT=null;resume()},setLayout(value){layout=value;lastT=null;draw()},
  setStill(value){still=value;if(still)parts=[];cancelAnimationFrame(raf);raf=0;lastT=null;draw(0);resume()},
  celebrate(xRatio,yRatio){if(dead||still||document.hidden||!visible)return;parts=[];const r=host.getBoundingClientRect();const burst=(x,y,delay=0)=>{const colors=['#ff477d','#fff9ec','#efb62f'];for(let i=0;i<40;i++){const a=i*Math.PI*2/40,v=28+Math.random()*50;parts.push({x,y,vx:Math.cos(a)*v,vy:Math.sin(a)*v,age:0,color:colors[i%3],r:1+Math.random()*1.6,delay})}};if(Number.isFinite(xRatio)&&Number.isFinite(yRatio))burst(r.width*djClamp15(xRatio),r.height*djClamp15(yRatio));else [[.24,.38],[.76,.27],[.54,.17]].forEach(([x,y],i)=>burst(r.width*x,r.height*y,i*.26));lastFrame=performance.now();resume()},
  finale(){if(dead||still||document.hidden||!visible)return;parts=[];const r=host.getBoundingClientRect(),colors=['#ff477d','#efb62f','#6ee7f9','#c4a1ff','#ff9f6b','#fff9ec'];[[.5,.2],[.22,.34],[.78,.3],[.36,.12],[.64,.15],[.1,.2],[.9,.18],[.5,.38],[.3,.26],[.7,.24]].forEach(([x,y],j)=>{for(let i=0;i<64;i++){const outer=i%4!==0,a=i*Math.PI*2/64+Math.random()*.06,v=outer?46+Math.random()*30:14+Math.random()*18;parts.push({x:r.width*x,y:r.height*y,vx:Math.cos(a)*v,vy:Math.sin(a)*v,age:0,color:i%7===0?'#fff9ec':colors[j%colors.length],r:1.1+Math.random()*1.7,delay:j*.17,life:2.5})}});lastFrame=performance.now();resume()},
  renderAt(t){draw(t)},diagnostics(){return {snapshot,costs:[...costs],layout:sceneLayout(host.clientWidth,host.clientHeight),raf,dead,particles:parts.length}},
  destroy(){dead=true;parts=[];cancelAnimationFrame(raf);raf=0;observer.disconnect();document.removeEventListener('visibilitychange',visibility);window.removeEventListener('resize',resize);window.visualViewport?.removeEventListener('resize',resize);canvas.remove();for(const i of images)i.src='';for(const k in FL){FL[k].width=FL[k].height=0}skySign.core.width=skySign.glow.width=0;historyCache.clear();}
 };
}
"""
(ROOT / 'src/frontend/js/bdayscene-yuno.js').write_text('\n'.join(line.rstrip() for line in (header + body + footer).splitlines())+'\n', encoding='utf-8')
assets = ROOT / 'src/frontend/assets/birthday'
(assets / 'bgm').mkdir(exist_ok=True)
(assets / 'beat').mkdir(exist_ok=True)
tracks=json.loads((HANDOFF / 'beatdata.json').read_text(encoding='utf8'))
music=Path(r'C:\Users\User\Documents\pyworks\mewtype-scheduler-worktrees\devpapers\ref\bgm_easteregg_birthday')
for key,name in [('noctural','Noctural Run'),('midnight','Midnight Groove')]:
    track=dict(tracks[key]);bands=base64.b64decode(track.pop('bands'))
    (assets / 'beat' / (key+'.bin')).write_bytes(bands)
    (assets / 'beat' / (key+'.json')).write_text(json.dumps(track,sort_keys=True,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    shutil.copyfile(music/(name+'.mp3'), assets/'bgm'/(key+'.mp3'))
shutil.copyfile(HANDOFF/'ufo.png',assets/'ufo.png')

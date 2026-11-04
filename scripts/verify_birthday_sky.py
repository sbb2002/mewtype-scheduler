from pathlib import Path
import functools,http.server,threading,json,os
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
out=Path(os.environ['TEMP'])/'birthday-greeting-motion'
class Handler(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
 def copyfile(self,source,outputfile):
  try:super().copyfile(source,outputfile)
  except (ConnectionResetError,BrokenPipeError):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',8137),functools.partial(Handler,directory=str(root)))
threading.Thread(target=server.serve_forever,daemon=True).start()
results={}
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
  for width,height in [(1440,900),(390,844),(320,740)]:
   page=browser.new_page(viewport={'width':width,'height':height});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   def route(r):
    if '127.0.0.1' not in r.request.url:r.fulfill(content_type='application/json',body='{}')
    elif '/birthdayui.js' in r.request.url:r.fulfill(content_type='text/javascript',body=(root/'src/frontend/js/birthdayui.js').read_text(encoding='utf8')+';window.__birthday={get scene(){return ctrl},get audio(){return music},get player(){return player}};')
    elif '/bdayscene-yuno.js' in r.request.url:
     s=(root/'src/frontend/js/bdayscene-yuno.js').read_text(encoding='utf8').replace('return {whenReady,setBrightness','return {stopForTest(){cancelAnimationFrame(raf);raf=0},whenReady,setBrightness').replace('!introActive()&&age>=0&&age<1.6','!window.__noPulse&&!introActive()&&age>=0&&age<1.6').replace('for(const star of backgroundStars(t,skyPlanNow.ambientSeed))','for(const star of (window.__noStars?[]:backgroundStars(t,skyPlanNow.ambientSeed)))').replace('for(const burst of backgroundFireworks(t,skyPlanNow.ambient))','for(const burst of (window.__noFireworks?[]:backgroundFireworks(t,skyPlanNow.ambient)))')
     s=s.replace('for(const meteor of backgroundMeteors(t,skyPlanNow.ambient))','for(const meteor of (window.__noMeteors?[]:backgroundMeteors(t,skyPlanNow.ambient)))');r.fulfill(content_type='text/javascript',body=s)
    else:r.continue_()
   page.route('**/*',route);page.goto('http://127.0.0.1:8137/src/frontend/?bday=yuno&ufo=zig');page.wait_for_function('window.__birthday?.player && __birthday.audio')
   page.evaluate('()=>{__birthday.audio.pause();__birthday.scene.stopForTest();__birthday.scene.setIntro(()=>false)}')
   # 곡을 0초에서 정지시킨 테스트이므로 인트로의 CSS 감쇠만 캡처에서 해제한다.
   page.add_style_tag(content='#bday-bg,#bday-bg canvas{filter:brightness(1)!important}')
   metrics=page.evaluate('''async()=>{
    const {backgroundStars}=await import('./js/bdaystars.js');
    let maxCount=0,minCount=24;for(let t=0;t<60;t+=.1){const stars=backgroundStars(t);maxCount=Math.max(maxCount,stars.length);minCount=Math.min(minCount,stars.length);if(stars.some(s=>s.radius>2.6||s.alpha<0||s.alpha>.751))throw Error('Star bounds')}
    const ambient=__birthday.scene.diagnostics().ambient;
    for(const e of ambient.events)if(ambient.blocked.some(([a,b])=>e.start<b&&e.end>a))throw Error('Ambient overlaps fixed scene');
    const fireworkTime=ambient.events.find(e=>e.kind==='fireworks').start+1,meteorTime=ambient.events.find(e=>e.kind==='meteor').start+.75;
    const cv=document.querySelector('#bday-bg canvas'),c=cv.getContext('2d'),L=__birthday.scene.diagnostics().layout;
    function pixels(){return CanvasRenderingContext2D.prototype.getImageData.call(c,0,0,cv.width,cv.height).data}
    function diff(a,b,limit){let count=0;for(let y=0;y<limit;y++)for(let x=0;x<cv.width;x++){const i=(y*cv.width+x)*4;if(Math.abs(a[i]-b[i])+Math.abs(a[i+1]-b[i+1])+Math.abs(a[i+2]-b[i+2])>8)count++}return count}
    window.__noPulse=true;__birthday.scene.renderAt(18.1);let before=pixels();window.__noPulse=false;__birthday.scene.renderAt(18.1);let after=pixels();
    const pulseAboveOldBoundary=diff(before,after,Math.max(0,Math.floor(L.offsetY*cv.height/innerHeight)-2));
    window.__noPulse=true;window.__noStars=true;__birthday.scene.renderAt(35.1);before=pixels();window.__noStars=false;__birthday.scene.renderAt(35.1);after=pixels();const starPixels=diff(before,after,cv.height);
    __birthday.scene.setStill(true);window.__noStars=true;__birthday.scene.renderAt(35.1);before=pixels();window.__noStars=false;__birthday.scene.renderAt(35.1);after=pixels();const reducedStarPixels=diff(before,after,cv.height);
    __birthday.scene.setStill(false);__birthday.scene.stopForTest();window.__noFireworks=true;__birthday.scene.renderAt(fireworkTime);before=pixels();window.__noFireworks=false;__birthday.scene.renderAt(fireworkTime);after=pixels();const fireworkPixels=diff(before,after,cv.height);
    __birthday.scene.setStill(true);window.__noFireworks=true;__birthday.scene.renderAt(fireworkTime);before=pixels();window.__noFireworks=false;__birthday.scene.renderAt(fireworkTime);after=pixels();const reducedFireworkPixels=diff(before,after,cv.height);
    __birthday.scene.setStill(false);__birthday.scene.stopForTest();
    const original=c.drawImage,ufos=[];c.drawImage=function(image,...args){if(image.src?.endsWith('/ufo.png')){const m=c.getTransform();ufos.push({x:m.e*innerWidth/cv.width,y:m.f*innerHeight/cv.height})}return original.call(this,image,...args)};
    const track=await __birthday.audio.beat;for(const [birth,life] of [[track.beats[192],4.25],[track.beats[328],11.25]])for(let a=.4;a<life-.4;a+=.2)__birthday.scene.renderAt(birth+a);
    c.drawImage=original;const ufoVisible=ufos.filter(p=>p.x>0&&p.x<innerWidth&&p.y>0&&p.y<innerHeight*.68).length/ufos.length;
    window.__noMeteors=true;__birthday.scene.renderAt(meteorTime);before=pixels();window.__noMeteors=false;__birthday.scene.renderAt(meteorTime);after=pixels();const meteorPixels=diff(before,after,cv.height);
    window.__noPulse=false;__birthday.scene.renderAt(18.1);
    return {events:ambient.events.length,blocked_overlap:false,meteorPixels,maxCount,minCount,pulseAboveOldBoundary,starPixels,reducedStarPixels,fireworkPixels,reducedFireworkPixels,ufoVisible,ufoSamples:ufos.length};
   }''')
   assert metrics['starPixels']>5 and metrics['reducedStarPixels']==0,metrics
   assert metrics['maxCount']>2 and metrics['minCount']<metrics['maxCount'],metrics
   assert metrics['meteorPixels']>20,metrics
   assert metrics['fireworkPixels']>20 and metrics['reducedFireworkPixels']==0,metrics
   if width<700:assert metrics['ufoVisible']>.85 and metrics['ufoSamples']>30,metrics
   if width<700:assert metrics['pulseAboveOldBoundary']>100,metrics
   page.screenshot(path=str(out/f'{width}-pulse.png'))
   priority=page.evaluate('''async()=>{
    const {setMainMusicActive}=await import('./js/musicpriority.js'),audio=__birthday.audio;
    await audio.play();if(audio.paused)throw Error('BGM did not start');
    setMainMusicActive(true);if(!audio.paused||audio.diagnostics().scheduled.length)throw Error('Priority did not stop BGM');
    setMainMusicActive(false);await audio.play();
    const deadline=performance.now()+20000;while(!audio.diagnostics().decoded&&performance.now()<deadline)await new Promise(r=>setTimeout(r,50));
    if(!audio.diagnostics().decoded)throw Error('Buffer decode timeout');
    setMainMusicActive(true);if(!audio.paused||audio.diagnostics().scheduled.length)throw Error('Priority did not clear buffer queue');
    await audio.play();if(!audio.paused)throw Error('BGM restarted over main player');
    setMainMusicActive(false);if(!audio.paused)throw Error('Unexpected auto resume');
    const pending=audio.play();setMainMusicActive(true);await pending;if(!audio.paused)throw Error('Pending play race');
    setMainMusicActive(false);await audio.play();if(audio.paused)throw Error('Manual resume failed');audio.pause();
    return {priority_pause:true,buffer_queue_cleared:true,blocked_restart:true,no_auto_resume:true,pending_play_cancelled:true,manual_resume:true};
   }''')
   assert not errors,errors
   results[str(width)]={**metrics,'priority':priority};page.close()
  browser.close()
finally:server.shutdown()
(out/'sky.json').write_text(json.dumps(results,sort_keys=True,indent=2)+'\n',encoding='utf8');print(json.dumps(results))

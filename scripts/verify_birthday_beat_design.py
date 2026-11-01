"""박자 패널 캡처와 큰 펄스의 동일 캔버스 비용·반경을 비교한다."""
from pathlib import Path
import functools,http.server,threading,tempfile,json
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(tempfile.gettempdir())/'birthday-story'/'beat-controls';OUT.mkdir(parents=True,exist_ok=True)
# 이번 편집 전 큰 펄스. 운영 코드는 바꾸지 않고 브라우저 테스트 응답에만 비교 함수를 넣는다.
BEFORE='''function beforeBigPulse(c,age){
 const life=PULSE_LIFE.big,e=djEase15(age/.09)*djEase15((life-age)/.3),g=c.createLinearGradient(400,-100,1300,500);g.addColorStop(0,P);g.addColorStop(.33,'#ffd36b');g.addColorStop(.66,V);g.addColorStop(1,C);
 for(let wave=0;wave<3;wave++){const a=age-wave*.22;if(a<0)continue;const u=a/(life-.44);if(u>=1)continue;
  for(let j=3;j>=0;j--){const r=104+1150*u-30*j;if(r<75)continue;
   c.globalAlpha=e*(1-.8*u)*(.95-j*.17);c.strokeStyle=g;c.shadowColor=j%2?C:P;c.shadowBlur=26;c.lineWidth=(20-15*u)*(1-j*.15);c.beginPath();c.arc(850,267,r,0,Math.PI*2);c.stroke();
   if(j===0){c.globalAlpha=e*.1*(1-u);c.lineWidth=90;c.stroke()}
  }
 }
 const u=age/life;c.shadowBlur=14;c.lineWidth=4;c.strokeStyle='#ffe9b0';c.globalAlpha=e*.85*(1-u);
 for(let j=0;j<48;j++){const ang=j*Math.PI/24,inner=118+240*u,len=(j%2?70:150)*(1-u);c.beginPath();c.moveTo(850+Math.cos(ang)*inner,267+Math.sin(ang)*inner);c.lineTo(850+Math.cos(ang)*(inner+len),267+Math.sin(ang)*(inner+len));c.stroke()}c.shadowBlur=0;
}
'''
EXTRA='''return {
 stopForTest(){cancelAnimationFrame(raf);raf=0},
 pulseFrame(big,age){still=false;pulses.length=0;pulses.push({start:performance.now()/1000-age,big});draw(clock());cancelAnimationFrame(raf);raf=0},
 pulseAudit(){
  const cv=document.createElement('canvas');cv.width=1200;cv.height=760;const ctx=cv.getContext('2d'),rows={};
  for(const [name,fn] of [['small',sunPulse],['before',beforeBigPulse],['after',sunBigPulse]]){
   let maxRadius=0,strokes=0;const arc=ctx.arc.bind(ctx),stroke=ctx.stroke.bind(ctx);
   ctx.arc=(x,y,r,...args)=>{maxRadius=Math.max(maxRadius,r);return arc(x,y,r,...args)};ctx.stroke=()=>{strokes++;return stroke()};
   ctx.save();fn(ctx,.9);ctx.restore();ctx.arc=arc;ctx.stroke=stroke;
   rows[name]={maxRadius,strokes};
  }
  for(const [name,fn] of [['before',beforeBigPulse],['after',sunBigPulse]]){
   const times=[];for(let i=0;i<32;i++){ctx.clearRect(0,0,1200,760);const start=performance.now();ctx.save();fn(ctx,.3+(i%12)*.1);ctx.restore();ctx.getImageData(0,0,1200,760);if(i>=8)times.push(performance.now()-start)}
   times.sort((a,b)=>a-b);rows[name].medianMs=times[Math.floor(times.length/2)];rows[name].p95Ms=times[Math.floor(times.length*.95)];
  }
  cv.width=cv.height=0;return rows;
 },skyBusy(t)'''
class Handler(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
results={}
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
  for width,height,touch in [(1440,900,False),(390,844,True),(320,568,True),(740,360,False),(740,360,True)]:
   key=f'{width}x{height}'+('-touch' if width==740 and touch else '')
   context=browser.new_context(viewport={'width':width,'height':height},is_mobile=touch,has_touch=touch)
   context.add_init_script("localStorage.setItem('bday-yuno-controls-unlocked-v1','1')")
   page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   def route(r):
    if '127.0.0.1' not in r.request.url:r.fulfill(content_type='application/json',body='{}')
    elif '/birthdayui.js' in r.request.url:r.fulfill(content_type='text/javascript',body=(ROOT/'src/frontend/js/birthdayui.js').read_text(encoding='utf8')+';window.__birthday={get scene(){return ctrl},get audio(){return music},teardown};')
    elif '/bdayscene-yuno.js' in r.request.url:
     s=(ROOT/'src/frontend/js/bdayscene-yuno.js').read_text(encoding='utf8').replace('function sunBigPulse(c,age){',BEFORE+'function sunBigPulse(c,age){').replace('return {skyBusy(t)',EXTRA)
     r.fulfill(content_type='text/javascript',body=s)
    else:r.continue_()
   page.route('**/*',route);page.goto(f'http://127.0.0.1:{server.server_port}/src/frontend/?bday=yuno')
   page.wait_for_function('window.__birthday?.scene && document.documentElement.hasAttribute("data-bday-started")')
   page.evaluate('async()=>{__birthday.audio.pause();await __birthday.audio.seek(19.05)}');page.wait_for_selector('[data-unlocked]',state='attached')
   page.evaluate('()=>{for(const a of document.getAnimations())if(Number.isFinite(a.effect.getComputedTiming().endTime))a.finish();__birthday.scene.setIntro(()=>false);__birthday.scene.stopForTest()}')
   def shot(name):
    path=OUT/f'{key}-{name}.png';page.screenshot(path=str(path))
    with Image.open(path) as im:im.resize((width*2,height*2)).save(path.with_stem(path.stem+'-2x'))
   shot('ready')
   page.evaluate('__birthday.scene.pulseFrame(false,.9)');shot('small-pulse')
   page.evaluate('__birthday.scene.pulseFrame(true,.9)');shot('big-pulse')
   if width==1440:
    audit=page.evaluate('__birthday.scene.pulseAudit()')
    assert audit['after']['maxRadius']>audit['small']['maxRadius']*1.6,audit
    assert audit['after']['strokes']<=audit['before']['strokes'],audit
    assert audit['after']['medianMs']<=audit['before']['medianMs']*1.35+1,audit
    results['pulse_audit']=audit
   bar=page.locator('.bday-music__bar').bounding_box();assert bar['height']<=(88 if width<700 else 54)
   for button in page.locator('.bday-music__bar button').all():
    box=button.bounding_box();assert box['width']>=44 and box['x']>=12 and box['x']+box['width']<=width-12,box
   results[key]={'bar':bar,'errors':errors}
   assert not errors,errors;page.evaluate('__birthday.teardown()');context.close()
  browser.close()
finally:server.shutdown()
(OUT/'design-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(results,ensure_ascii=False,indent=2))

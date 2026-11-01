"""2차 연출 중간 프레임·희소성·피날레 보류를 실제 Chromium에서 검사한다."""
from pathlib import Path
import functools,http.server,threading,json,tempfile
from playwright.sync_api import sync_playwright
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(tempfile.gettempdir())/'birthday-story'/'round2'
OUT.mkdir(parents=True,exist_ok=True)
class Handler(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
 def copyfile(self,source,outputfile):
  try:super().copyfile(source,outputfile)
  except (ConnectionResetError,BrokenPipeError):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
results={}
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
  for width,height in [(1440,900),(390,844),(320,568),(740,360)]:
   context=browser.new_context(viewport={'width':width,'height':height})
   context.add_init_script("localStorage.setItem('bday-yuno-controls-unlocked-v1','1')")
   page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   def route(r):
    if '127.0.0.1' not in r.request.url:r.fulfill(content_type='application/json',body='{}')
    elif '/birthdayui.js' in r.request.url:
     r.fulfill(content_type='text/javascript',body=(ROOT/'src/frontend/js/birthdayui.js').read_text(encoding='utf8')+';window.__birthday={get scene(){return ctrl},get audio(){return music},teardown};')
    elif '/bdayscene-yuno.js' in r.request.url:
     s=(ROOT/'src/frontend/js/bdayscene-yuno.js').read_text(encoding='utf8')
     s=s.replace('const SKY_SALT=','let SKY_SALT=').replace('function playFinale(){','function playFinale(){window.__finaleRuns=(window.__finaleRuns||0)+1;')
     s=s.replace('return {skyBusy(t)', '''return {
      testPlan(){return skyPlan(TRK)},stopForTest(){cancelAnimationFrame(raf);raf=0},
      testState(){return {pendingFinale,manual,particles:parts.length}},
      samplePlans(){const saved=SKY_SALT,rows=[];for(let salt=0;salt<100;salt++){
       SKY_SALT=salt;const plan=skyPlan({...TRK}),base=plan.blocked.filter(([a,b])=>!plan.showers.some(t=>a===t&&b===t+5));
       rows.push({styles:plan.ufos.map(u=>u.zig.style),showers:plan.showers.length,ambient:plan.ambient.length,before:createAmbientTimeline(TRK.duration,base,plan.ambientSeed).length});
      }SKY_SALT=saved;return rows},
      skyBusy(t)''')
     r.fulfill(content_type='text/javascript',body=s)
    else:r.continue_()
   page.route('**/*',route)
   page.goto(f'http://127.0.0.1:{server.server_port}/src/frontend/?bday=yuno&ufo=sign')
   page.wait_for_function('window.__birthday?.scene && __birthday.audio');page.wait_for_timeout(600)
   page.evaluate('async()=>{__birthday.audio.pause();await __birthday.audio.seek(19.05)}')
   page.wait_for_selector('[data-bday-revealed]',state='attached')
   page.evaluate('()=>{for(const a of document.getAnimations())if(Number.isFinite(a.effect.getComputedTiming().endTime))a.finish()}')
   page.evaluate('async()=>{await __birthday.audio.seek(31)}')
   page.wait_for_timeout(100)
   page.evaluate('()=>{__birthday.scene.stopForTest();__birthday.scene.setIntro(()=>false);__birthday.scene.renderAt(31)}')
   def shot(name):
    path=OUT/f'{width}x{height}-{name}.png';page.screenshot(path=str(path))
    with Image.open(path) as img:
     img.resize((width*2,height*2)).save(OUT/f'{width}x{height}-{name}-2x.png')
   page.evaluate('()=>{for(const a of document.querySelector(".bday-story").getAnimations({subtree:true})){a.pause();a.currentTime=350}}')
   shot('text-middle')
   text=page.locator('.bday-story__text')
   assert text.evaluate('e=>e.scrollWidth<=e.clientWidth')
   glyphs=page.locator('.bday-story__glyph').evaluate_all('es=>es.map(e=>+getComputedStyle(e).opacity)')
   assert max(glyphs)>min(glyphs),glyphs
   page.evaluate('()=>{for(const a of document.getAnimations())if(Number.isFinite(a.effect.getComputedTiming().endTime))a.finish()}')
   page.evaluate('()=>{document.querySelector(".bday-music").setAttribute("data-fresh-unlock","")}')
   page.wait_for_timeout(50)
   page.evaluate('()=>{for(const a of document.querySelector(".bday-music__bar").getAnimations({subtree:true})){a.pause();a.currentTime=460}}')
   shot('expand-middle')
   for button in page.locator('.bday-effects button').all():
    b=button.bounding_box();assert b['x']>=12 and b['x']+b['width']<=width-12,b
   page.evaluate('()=>{for(const a of document.getAnimations())if(Number.isFinite(a.effect.getComputedTiming().endTime))a.finish()}')
   page.wait_for_function('!document.querySelector("[data-fresh-unlock]")')
   page.mouse.move(1,1);page.wait_for_timeout(100);page.evaluate('document.querySelector(".bday-music").classList.add("idle")');page.wait_for_timeout(1400)
   assert page.locator('.bday-music__bar').evaluate('e=>+getComputedStyle(e).opacity')<.6,page.locator('.bday-music__bar').evaluate('e=>({opacity:getComputedStyle(e).opacity,idle:e.parentElement.className,animations:e.getAnimations().map(a=>({name:a.animationName,state:a.playState,time:a.currentTime}))})')
   page.evaluate('document.querySelector(".bday-music").classList.remove("idle")')
   tracks=[]
   for index in range(2):
    if index:
     page.evaluate('async()=>{await __birthday.audio.next();__birthday.scene.setTrack(await __birthday.audio.beat);__birthday.scene.stopForTest()}')
    plan=page.evaluate('__birthday.scene.testPlan()');samples=page.evaluate('__birthday.scene.samplePlans()')
    assert {s for r in samples for s in r['styles']}=={'curve','angle','mixed'},'UFO 궤적 세 종류'
    assert all(2<=r['showers']<=3 and r['ambient']>=3 for r in samples),samples
    assert all(abs(a-b)>=24 for i,a in enumerate(plan['showers']) for b in plan['showers'][i+1:])
    tracks.append({'count':len(plan['showers']),'times':plan['showers'],'ambient':len(plan['ambient']),
                   'sample_count_range':[min(r['showers'] for r in samples),max(r['showers'] for r in samples)],
                   'ambient_before_mean':sum(r['before'] for r in samples)/100,'ambient_after_mean':sum(r['ambient'] for r in samples)/100})
    if not index:
     page.evaluate('async t=>{await __birthday.audio.seek(t);for(const a of document.querySelector(".bday-story").getAnimations({subtree:true}))if(Number.isFinite(a.effect.getComputedTiming().endTime))a.finish();__birthday.scene.renderAt(t)}',plan['constellation']+1.8);shot('constellation-pop')
     page.evaluate('t=>__birthday.scene.renderAt(t)',plan['constellation']+4.5);shot('constellation-rainbow')
     page.evaluate('async t=>{await __birthday.audio.seek(t);__birthday.scene.renderAt(t)}',plan['showers'][0]+1.05);shot('shower')
   # 피날레 한 건만 보류하고 반복 입력 후 마지막 조작 3초에 한 번 재생한다.
   page.evaluate('()=>{window.__finaleRuns=0;__birthday.scene.triggerManual("sign");__birthday.scene.finale();__birthday.scene.finale()}')
   assert page.evaluate('__birthday.scene.testState().pendingFinale')
   page.wait_for_timeout(300);page.evaluate('__birthday.scene.triggerManual("shower")')
   page.wait_for_timeout(2400);assert page.evaluate('__birthday.scene.testState().pendingFinale')
   page.wait_for_timeout(750)
   state=page.evaluate('__birthday.scene.testState()')
   assert not state['pendingFinale'] and state['manual'] is None and state['particles']>0,state
   page.wait_for_timeout(500);assert page.evaluate('window.__finaleRuns')==1
   page.emulate_media(reduced_motion='reduce')
   page.evaluate('document.querySelector(".bday-music").setAttribute("data-fresh-unlock","")')
   assert page.locator('.bday-panel-scan').evaluate('e=>getComputedStyle(e).display')=='none'
   assert page.locator('.bday-effects button').first.evaluate('e=>getComputedStyle(e).animationName')=='none'
   page.evaluate('__birthday.teardown()');assert not errors,errors
   results[f'{width}x{height}']={'tracks':tracks,'text_stagger':True,'fresh_cleanup_idle':True,'finale_deferred_once':True,'reduced_expansion':True,'errors':errors}
   context.close()
  browser.close()
finally:server.shutdown()
(OUT/'round2-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(results,ensure_ascii=False,indent=2))

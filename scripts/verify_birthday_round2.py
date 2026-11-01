"""2차 연출 중간 프레임·희소성·피날레 보류를 실제 Chromium에서 검사한다."""
from pathlib import Path
import functools,http.server,threading,json,tempfile
from playwright.sync_api import sync_playwright
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(tempfile.gettempdir())/'birthday-story'/'round7'
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
     s=s.replace('function draw(t=clock()) {','function draw(t=clock()) {window.__draws=(window.__draws||0)+1;').replace('function skyProps(c,t){','function skyProps(c,t){window.__routineCalls=(window.__routineCalls||0)+1;')
     s=s.replace('if(t1<=t0)return;','if(t1<=t0)return;window.__trailSegments=(window.__trailSegments||0)+170;').replace('skySignDraw(c,f,age);','window.__signCalls=(window.__signCalls||0)+1;skySignDraw(c,f,age);')
     s=s.replace('const SKY_SALT=','let SKY_SALT=').replace('function playFinale(){','function playFinale(){window.__finaleRuns=(window.__finaleRuns||0)+1;')
     s=s.replace('return {skyBusy(t)', '''return {
      testPlan(){return skyPlan(TRK)},stopForTest(){cancelAnimationFrame(raf);raf=0},
      testState(){return {pendingFinale,manual,effects:[...manualEffects.values()],toggles,toggleParticles,particles:parts.length}},
      ageEffects(seconds){for(const e of manualEffects.values())e.start-=seconds;draw(clock())},
      ageToggles(seconds){for(const e of Object.values(toggles))if(e)e.start-=seconds;draw(clock())},
      expireEffects(){for(const e of manualEffects.values())e.start-=e.dur+1;if(manual)manual.start-=manual.dur+1;draw(clock())},
      pathMetrics(){const e=manualEffects.get('ufo'),pts=Array.from({length:101},(_,i)=>skyZig(e.f,i/100));return {style:e.f.zig.style,yRange:Math.max(...pts.map(p=>p[1]))-Math.min(...pts.map(p=>p[1])),points:e.f.zig.pts}},
      samplePlans(){const saved=SKY_SALT,rows=[];for(let salt=0;salt<100;salt++){
       SKY_SALT=salt;const plan=skyPlan({...TRK}),base=plan.blocked.filter(([a,b])=>!plan.showers.some(t=>a===t&&b===t+5));
       rows.push({styles:plan.ufos.map(u=>u.zig.style),showers:plan.showers.length,ambient:plan.ambient.length,before:createAmbientTimeline(TRK.duration,base,plan.ambientSeed).length});
      }SKY_SALT=saved;return rows},
      skyBusy(t)''')
     r.fulfill(content_type='text/javascript',body=s)
    elif '/bdaystory.js' in r.request.url:
     r.fulfill(content_type='text/javascript',body=(ROOT/'src/frontend/js/bdaystory.js').read_text(encoding='utf8').replace('const talk=!reward.unlocked','const talk=true'))
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
     page.evaluate('async()=>{await __birthday.audio.next();__birthday.audio.pause();__birthday.scene.setTrack(await __birthday.audio.beat);__birthday.scene.stopForTest()}')
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
     page.evaluate('t=>__birthday.scene.renderAt(t)',plan['constellation']+7.2);shot('constellation-flash')
     page.evaluate('async t=>{await __birthday.audio.seek(t);__birthday.scene.renderAt(t)}',plan['showers'][0]+1.05);shot('shower')
   # 토글은 정지 중에도 그리고, 숨김 복귀 시 주기를 새로 시작한다.
   for label in ['폭죽','유성우']:
    effect=page.get_by_role('button',name=label,exact=True)
    if label=='폭죽': # 폭죽은 클릭 = 단발, 길게 = 토글
     box=effect.bounding_box();page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);page.mouse.down();page.wait_for_function('e=>e.hasAttribute("data-charged")',arg=effect.element_handle(),timeout=5000);page.mouse.up()
    else:effect.click()
    assert effect.get_attribute('aria-pressed')=='true'
   before=page.evaluate('window.__draws');page.wait_for_timeout(200)
   assert page.evaluate('window.__draws')>before and page.evaluate('__birthday.audio.paused')
   page.evaluate('()=>{window.__routineCalls=0;__birthday.scene.ageToggles(17.3)}');shot('toggle-salvo')
   assert page.evaluate('window.__routineCalls')>0
   cap=420 if width<700 else 720
   assert 0<page.evaluate('__birthday.scene.testState().toggleParticles')<=cap
   page.evaluate('__birthday.scene.ageToggles(3.1)');shot('toggle-comet')
   page.evaluate('()=>{Object.defineProperty(document,"hidden",{configurable:true,value:true});document.dispatchEvent(new Event("visibilitychange"))}')
   page.wait_for_timeout(100)
   page.evaluate('__birthday.scene.ageToggles(120)')
   page.evaluate('()=>{delete document.hidden;document.dispatchEvent(new Event("visibilitychange"))}')
   ages=page.evaluate('Object.values(__birthday.scene.testState().toggles).map(e=>performance.now()/1000-e.start)')
   assert all(a<.5 for a in ages),ages
   for label in ['폭죽','유성우']:
    effect=page.get_by_role('button',name=label,exact=True)
    if label=='폭죽':
     box=effect.bounding_box();page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);page.mouse.down();page.wait_for_function('e=>e.hasAttribute("data-charged")',arg=effect.element_handle(),timeout=5000);page.mouse.up()
    else:effect.click()
    assert page.get_by_role('button',name=label,exact=True).get_attribute('aria-pressed')=='false'
   page.wait_for_function('!__birthday.scene.testState().toggles.fireworks&&!__birthday.scene.testState().toggles.shower',timeout=8000) # 끈 뒤에는 이미 나온 효과가 끝나야 비워진다
   # 원래 UFO·사인 렌더러, 동시 재생, 같은 종류 재시작, 마지막 수명 종료의 피날레를 검사한다.
   assert page.evaluate('__birthday.audio.paused')
   page.get_by_role('button',name='UFO',exact=True).click()
   page.evaluate('()=>{window.__trailSegments=0;window.__signCalls=0;__birthday.scene.ageEffects(1.4)}')
   metrics=page.evaluate('__birthday.scene.pathMetrics()');assert metrics['yRange']>60,metrics
   assert page.evaluate('window.__trailSegments')>0
   shot('manual-ufo')
   page.evaluate('__birthday.scene.triggerManual("sign")');page.wait_for_timeout(120)
   page.evaluate('__birthday.scene.ageEffects(1.2)');shot('manual-both')
   state=page.evaluate('__birthday.scene.testState()')
   assert {e['kind'] for e in state['effects']}=={'sign','ufo'}
   assert page.evaluate('window.__signCalls')>0
   old=metrics['points'];page.evaluate('__birthday.scene.triggerManual("ufo")')
   assert page.evaluate('__birthday.scene.pathMetrics().points')!=old
   assert len(page.evaluate('__birthday.scene.testState().effects'))==2
   page.evaluate('()=>{window.__finaleRuns=0;__birthday.scene.finale();__birthday.scene.finale()}')
   assert page.evaluate('__birthday.scene.testState().pendingFinale')
   page.evaluate('__birthday.scene.ageEffects(3.1)')
   assert page.evaluate('__birthday.scene.testState().pendingFinale')
   page.evaluate('__birthday.scene.expireEffects()');page.wait_for_timeout(150)
   state=page.evaluate('__birthday.scene.testState()')
   assert not state['pendingFinale'] and not state['effects'] and state['particles']>0,state
   assert page.evaluate('window.__finaleRuns')==1
   page.evaluate('()=>{__birthday.scene.triggerManual("fireworks");__birthday.scene.ageToggles(17.3)}')
   shared=page.evaluate('__birthday.scene.testState()')
   assert shared['particles']+shared['toggleParticles']<=(1900 if width<700 else 3200)
   page.evaluate('__birthday.scene.triggerManual("fireworks")')
   page.evaluate('()=>{__birthday.scene.triggerManual("fireworks");__birthday.scene.triggerManual("shower");__birthday.scene.setStill(true);__birthday.scene.ageToggles(1.3)}');shot('toggles-reduced')
   assert page.evaluate('__birthday.scene.testState().toggleParticles')<=108
   page.evaluate('()=>{__birthday.scene.triggerManual("fireworks");__birthday.scene.triggerManual("shower")}')
   page.emulate_media(reduced_motion='reduce')
   page.evaluate('document.querySelector(".bday-music").setAttribute("data-fresh-unlock","")')
   assert page.locator('.bday-panel-scan').evaluate('e=>getComputedStyle(e).display')=='none'
   assert page.locator('.bday-effects button').first.evaluate('e=>getComputedStyle(e).animationName')=='none'
   page.evaluate('__birthday.teardown()');assert not errors,errors
   results[f'{width}x{height}']={'tracks':tracks,'text_stagger':True,'fresh_cleanup_idle':True,'finale_deferred_once':True,'ufo_path':metrics,'manual_sign_renderer':True,'independent_manual_effects':True,'toggle_on_off_paused':True,'hidden_no_backlog':True,'particle_cap':cap,'trail_segments':page.evaluate('window.__trailSegments'),'sign_renderer_calls':page.evaluate('window.__signCalls'),'reduced_expansion':True,'errors':errors}
   context.close()
  browser.close()
finally:server.shutdown()
(OUT/'round2-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(results,ensure_ascii=False,indent=2))

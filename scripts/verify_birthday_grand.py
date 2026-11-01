"""밤 풍경 더 보기의 사인을 UFO 가 그리는지 실제 Chromium 에서 검사한다."""
from pathlib import Path
import base64,functools,http.server,threading,tempfile,re
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(tempfile.gettempdir())/'birthday-story'/'grand'
OUT.mkdir(parents=True,exist_ok=True)
class Handler(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
 def copyfile(self,source,outputfile):
  try:super().copyfile(source,outputfile)
  except (ConnectionResetError,BrokenPipeError):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
HOOK="""
localStorage.setItem('bday-yuno-controls-unlocked-v1','1');
window.__ufoDraws=0;window.__forceTalk=true;window.__toDataURL=HTMLCanvasElement.prototype.toDataURL;
const drawImage=CanvasRenderingContext2D.prototype.drawImage;
CanvasRenderingContext2D.prototype.drawImage=function(image,...rest){
 if(/ufo/i.test(image?.src||''))window.__ufoDraws++;
 return drawImage.call(this,image,...rest);
};
"""
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
  for width,height in [(1440,900),(390,844)]:
   context=browser.new_context(viewport={'width':width,'height':height})
   context.add_init_script(HOOK)
   page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   def route(r):
    if '127.0.0.1' not in r.request.url:r.fulfill(content_type='application/json',body='{}')
    elif '/birthdayui.js' in r.request.url:
     r.fulfill(content_type='text/javascript',body=(ROOT/'src/frontend/js/birthdayui.js').read_text(encoding='utf8')+';window.__birthday={get scene(){return ctrl},get audio(){return music},teardown};')
    elif '/bdayscene-yuno.js' in r.request.url:
     r.fulfill(content_type='text/javascript',body=(ROOT/'src/frontend/js/bdayscene-yuno.js').read_text(encoding='utf8').replace("function addPulse(big,wave){","function addPulse(big,wave){(window.__pulseLog??=[]).push(big?'pulse-big':wave?wave.name:'pulse');").replace('return {skyBusy(t)','return {testPlan(){return skyPlan(TRK)},stopForTest(){cancelAnimationFrame(raf);raf=0},testGrand(a){manual.start=performance.now()/1000-a;cancelAnimationFrame(raf);raf=0;draw(clock());return {reveal:manual.f.reveal,end:manual.f.end}},testSign(a){const e=manualEffects.get("sign");e.start=performance.now()/1000-a;cancelAnimationFrame(raf);raf=0;draw(clock())},resumeForTest(){resume()},testFrame(){return window.__toDataURL.call(canvas,"image/png")},testState(){return {shots:shots.length,pulses:pulses.length,fireworks:!!toggles.fireworks,stopping:!!toggles.fireworks?.stopAt,shower:!!toggles.shower,effects:[...manualEffects.keys()]}},skyBusy(t)'))
    elif '/bdaystory.js' in r.request.url:
     r.fulfill(content_type='text/javascript',body=(ROOT/'src/frontend/js/bdaystory.js').read_text(encoding='utf8').replace('const talk=!reward.unlocked','const talk=!reward.unlocked||window.__forceTalk'))
    elif '/bdaystorylogic.js' in r.request.url:
     r.fulfill(content_type='text/javascript',body=(ROOT/'src/frontend/js/bdaystorylogic.js').read_text(encoding='utf8').replace('SILENT_NUDGE_MS=60000','SILENT_NUDGE_MS=1500'))
    else:r.continue_()
   page.route('**/*',route)
   page.goto(f'http://127.0.0.1:{server.server_port}/src/frontend/?bday=yuno&ufo=sign')
   page.wait_for_function('window.__birthday?.scene && __birthday.audio');page.wait_for_timeout(600)
   page.evaluate('async()=>{__birthday.audio.pause();await __birthday.audio.seek(19.05)}')
   page.wait_for_selector('[data-bday-revealed]',state='attached')
   page.evaluate('()=>{for(const a of document.getAnimations())if(Number.isFinite(a.effect.getComputedTiming().endTime))a.finish()}')
   page.evaluate('async()=>{await __birthday.audio.seek(31)}')
   page.wait_for_timeout(300)
   page.wait_for_selector('.bday-story.is-visible')
   page.evaluate('__birthday.audio.setVolume(0)');page.wait_for_selector('.bday-story:not(.is-visible)',state='attached')
   # 무음이면 후광 · LED 의 비트 피크가 1/100 로 줄어든다(같은 시각 비교, 바닥값 .3칸 제외).
   peaks=lambda:page.evaluate('()=>{const s=__birthday.scene;s.renderAt(120.3);const d=s.diagnostics().snapshot;return [Math.max(...d.heights)/9.5,Math.max(...d.lengths)]}')
   quiet=peaks();page.evaluate('__birthday.audio.setVolume(.3)');loud=peaks()
   assert max(quiet[0]-.3,0)<=max(loud[0]-.3,.01)*.02 and quiet[1]<20<loud[1],(quiet,loud)
   page.wait_for_selector('.bday-story.is-visible')
   grand=page.locator('.bday-effects .grand');sign=page.locator('.bday-effects .sign');fire=page.locator('.bday-effects .fireworks');pulse=page.locator('.bday-effects .pulse')
   state=lambda:page.evaluate('__birthday.scene.testState()')
   def hold(button):
    box=button.bounding_box();page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);page.mouse.down();page.wait_for_function('e=>e.hasAttribute("data-charged")',arg=button.element_handle(),timeout=5000);page.mouse.up()
   # 폭죽: 클릭 = 단발(쿨타임 0.1초), 길게 = 토글, 끄면 이미 나온 폭죽은 남는다.
   fire.click();page.wait_for_timeout(120);fire.click();page.wait_for_timeout(120);fire.click();assert state()['shots']==3,state()
   assert page.evaluate('()=>{const s=__birthday.scene;return [s.triggerManual("shot"),s.triggerManual("shot")]}')[1] is False
   hold(fire);assert state()['fireworks'] and fire.get_attribute('aria-pressed')=='true'
   hold(fire);s=state();assert s['fireworks'] and s['stopping'] and fire.get_attribute('aria-pressed')=='false',s
   page.wait_for_function('!__birthday.scene.testState().fireworks',timeout=6000)
   # 펄스: 누르는 순간 + 길게 눌렀다 떼면 큰 펄스.
   pulse.click();hold(pulse);page.wait_for_function("(window.__pulseLog||[]).includes('pulse-big')",timeout=3000);log=page.evaluate('__pulseLog');assert log==['pulse','pulse','pulse-big'],log
   # 재생 중: 누르고 있는 동안 반 박마다, 떼면 다음 박에 큰 펄스.
   page.evaluate('async()=>{await __birthday.audio.play();window.__pulseLog=[]}')
   box=pulse.bounding_box();page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);page.mouse.down();page.wait_for_timeout(2500);page.mouse.up()
   page.wait_for_function("__pulseLog.includes('pulse-big')",timeout=3000);log=page.evaluate('__pulseLog');page.evaluate('__birthday.audio.pause()')
   waves=[x for x in log if x in ('small','back','medium')];assert log[-1]=='pulse-big' and 2<=len(waves)<=6 and ','.join(waves) in ','.join(['small','small','back','medium']*4),log
   page.screenshot(path=str(OUT/f'{width}x{height}-pulse-big.png'))
   # 별자리 · 사인: 클릭 = YMMT, 길게 = 사인, 나중에 누른 쪽으로 바뀐다.
   sign.click();assert state()['effects']==['ymmt'],state();page.wait_for_timeout(3000);page.screenshot(path=str(OUT/f'{width}x{height}-ymmt-button.png'))
   hold(sign);assert state()['effects']==['sign'],state()
   for age in (2.9,3.3):
    data=page.evaluate('a=>{__birthday.scene.testSign(a);return __birthday.scene.testFrame()}',age)
    (OUT/f'{width}x{height}-trail-{age}.png').write_bytes(base64.b64decode(data.split(',')[1]))
   page.evaluate('__birthday.scene.resumeForTest()')
   page.wait_for_function('!__birthday.scene.testState().effects.length',timeout=20000)
   before=page.evaluate('window.__ufoDraws')
   page.evaluate('''()=>{const b=document.querySelector(".bday-effects .grand");window.__grandStart=performance.now();new MutationObserver(()=>{if(!b.disabled)window.__grandEnd??=performance.now()}).observe(b,{attributes:true,attributeFilter:["disabled"]})}''')
   grand.click();assert sign.is_disabled()
   for at,gap in [('3s',3000),('6s',3000),('8s',2000),('10s',2000)]:
    page.wait_for_timeout(gap);page.screenshot(path=str(OUT/f'{width}x{height}-{at}.png'))
   during=page.evaluate('window.__ufoDraws')-before
   assert during>30,f'UFO 그리기 {during}회'
   page.wait_for_function('window.__grandEnd',timeout=8000)
   seconds=page.evaluate('(__grandEnd-__grandStart)/1000')
   assert 15<seconds<16.5,f'장면 길이 {seconds:.1f}초'
   hold(sign);page.wait_for_timeout(8000);page.screenshot(path=str(OUT/f'{width}x{height}-button-burst.png'))
   page.wait_for_function('!document.querySelector(".bday-effects .grand").disabled')
   plan=page.evaluate('__birthday.scene.testPlan().ufos[0]');assert plan['mode']=='sign'
   page.evaluate('t=>{__birthday.scene.stopForTest();__birthday.scene.setIntro(()=>false);__birthday.scene.renderAt(t)}',plan['birth']+plan['reveal']+2.5)
   page.screenshot(path=str(OUT/f'{width}x{height}-fixed-burst.png'))
   page.evaluate('__birthday.scene.grandShow()')
   for name,offset in [('lines',-.45),('flash',.3),('hold',3),('leaving',4.9)]:
    timing=page.evaluate('__birthday.scene.testGrand(0)')
    # 스크린샷은 느려 시각이 밀리므로 그린 직후의 캔버스를 그대로 저장한다.
    data=page.evaluate('a=>{__birthday.scene.testGrand(a);return __birthday.scene.testFrame()}',timing['reveal']+offset)
    (OUT/f'{width}x{height}-sync-{name}.png').write_bytes(base64.b64decode(data.split(',')[1]))
   # 해금 뒤 마지막 말: 밤 풍경이 끝나면 한 번 말하고 곡 대사는 없다. 무음 대사는 방문당 한 번.
   context2=browser.new_context(viewport={'width':width,'height':height});context2.add_init_script(HOOK);page=context2.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.route('**/*',route)
   page.goto(f'http://127.0.0.1:{server.server_port}/src/frontend/?bday=yuno')
   page.wait_for_function('window.__birthday?.scene && __birthday.audio');page.wait_for_timeout(600)
   page.evaluate('async()=>{await __birthday.audio.seek(19.05)}')
   page.wait_for_selector('[data-bday-revealed]',state='attached')
   page.evaluate('()=>{for(const a of document.getAnimations())if(Number.isFinite(a.effect.getComputedTiming().endTime))a.finish()}')
   page.evaluate('async()=>{await __birthday.audio.seek(31);window.__forceTalk=false}')
   page.wait_for_selector('.bday-story:not(.is-visible)',state='attached')
   page.evaluate('document.querySelector(".bday-memory button").click()')
   page.wait_for_function('document.querySelector(".bday-story__text")?.getAttribute("aria-label")?.includes("너의 턴이야")&&document.querySelector(".bday-story").classList.contains("is-visible")',timeout=20000)
   page.wait_for_selector('.bday-story:not(.is-visible)',state='attached',timeout=9000)
   page.wait_for_timeout(300);assert 'is-visible' not in page.locator('.bday-story').get_attribute('class')
   page.evaluate('__birthday.audio.setVolume(0)')
   page.wait_for_function('document.querySelector(".bday-story__text")?.getAttribute("aria-label")?.includes("안듣고")&&document.querySelector(".bday-story").classList.contains("is-visible")',timeout=6000)
   page.wait_for_selector('.bday-story:not(.is-visible)',state='attached',timeout=8000)
   page.wait_for_timeout(2000);assert 'is-visible' not in page.locator('.bday-story').get_attribute('class')
   context2.close()
   assert not errors,errors
   print(f'{width}x{height}: UFO {during}회 · 장면 {seconds:.1f}초')
   context.close()
  browser.close()
finally:
 server.shutdown()
print('OK',OUT)

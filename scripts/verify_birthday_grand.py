"""밤 풍경 더 보기의 사인을 UFO 가 그리는지 실제 Chromium 에서 검사한다."""
from pathlib import Path
import functools,http.server,threading,tempfile,re
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
window.__ufoDraws=0;
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
     r.fulfill(content_type='text/javascript',body=(ROOT/'src/frontend/js/bdayscene-yuno.js').read_text(encoding='utf8').replace('return {skyBusy(t)','return {testPlan(){return skyPlan(TRK)},stopForTest(){cancelAnimationFrame(raf);raf=0},skyBusy(t)'))
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
   page.evaluate('__birthday.audio.setVolume(.3)');page.wait_for_selector('.bday-story.is-visible')
   grand=page.locator('.bday-effects .grand');sign=page.get_by_role('button',name='사인')
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
   sign.click();page.wait_for_timeout(9000);page.screenshot(path=str(OUT/f'{width}x{height}-button-burst.png'))
   page.wait_for_function('!document.querySelector(".bday-effects .grand").disabled')
   plan=page.evaluate('__birthday.scene.testPlan().ufos[0]');assert plan['mode']=='sign'
   page.evaluate('t=>{__birthday.scene.stopForTest();__birthday.scene.setIntro(()=>false);__birthday.scene.renderAt(t)}',plan['birth']+plan['reveal']+2.5)
   page.screenshot(path=str(OUT/f'{width}x{height}-fixed-burst.png'))
   assert not errors,errors
   print(f'{width}x{height}: UFO {during}회 · 장면 {seconds:.1f}초')
   context.close()
  browser.close()
finally:
 server.shutdown()
print('OK',OUT)

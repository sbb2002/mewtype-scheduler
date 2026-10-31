"""구간별 문구·완주 카드와 실제 Canvas 사인/스캔의 화면 경계를 검사한다."""
from pathlib import Path
import functools,http.server,threading,json,os
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ['TEMP'])/'birthday-story';OUT.mkdir(exist_ok=True)
class Handler(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
 def copyfile(self,source,outputfile):
  try:super().copyfile(source,outputfile)
  except (ConnectionResetError,BrokenPipeError):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
BASE=f'http://127.0.0.1:{server.server_port}'
results={}
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
  for width,height in [(1440,900),(1920,600),(900,800),(390,844),(360,800),(320,568),(740,360)]:
   page=browser.new_page(viewport={'width':width,'height':height});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.route('**/fixture.html',lambda r:r.fulfill(content_type='text/html',body='<html data-bday-full data-bday-revealed><style>body{background:#170725;margin:0}</style><link rel="stylesheet" href="/src/frontend/css/bdayplayer.css"><div class="bday-music"></div></html>'))
   page.goto(BASE+'/fixture.html')
   page.evaluate('''async()=>{
    const {mountBirthdayStory}=await import('/src/frontend/js/bdaystory.js');const listeners=new Set();
    window.a={index:0,paused:true,audio:{currentTime:0},subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn)}};
    window.finaleCount=0;window.reduced=false;window.story=mountBirthdayStory({audio:a,scene:{finale(){finaleCount++}},shell:document.querySelector('.bday-music'),reduced:()=>window.reduced});
    window.jump=(index,time,paused=true)=>{a.index=index;a.audio.currentTime=time;a.paused=paused;for(const fn of listeners)fn()};
   }''')
   for index,time in [(0,31),(0,135),(0,205),(1,27),(1,176)]:
    page.evaluate('v=>jump(...v)',[index,time]);rect=page.locator('.bday-story__text').bounding_box()
    assert rect['x']>=12 and rect['x']+rect['width']<=width-12 and rect['y']>=0 and rect['y']+rect['height']<height-132,(width,height,rect)
    assert page.locator('.bday-story__text').evaluate('e=>e.scrollWidth<=e.clientWidth'),(width,height)
   page.evaluate('()=>jump(1,209,true)');assert page.evaluate('finaleCount')==0
   page.evaluate('()=>jump(1,209,false)');assert page.evaluate('finaleCount')==1
   page.evaluate('()=>jump(1,212,false)');page.locator('.bday-memory').wait_for(state='visible')
   card=page.locator('.bday-memory').bounding_box()
   assert card['x']>=12 and card['x']+card['width']<=width-12 and card['y']>=0 and card['y']+card['height']<height-120,(width,height,card)
   assert page.locator('.bday-memory').evaluate('e=>e.scrollHeight<=e.clientHeight+1&&e.scrollWidth<=e.clientWidth'),(width,height,'card overflow')
   page.evaluate('()=>{for(const a of document.getAnimations())a.finish()}');page.screenshot(path=str(OUT/f'{width}x{height}-card.png'))
   page.locator('.bday-memory button').click();page.evaluate('()=>{jump(0,0);jump(1,212,false)}');assert page.locator('.bday-memory').is_hidden() and page.evaluate('finaleCount')==1
   page.evaluate('()=>{story.destroy();window.reduced=true;story=null}');assert page.locator('.bday-memory').count()==0
   assert not errors,errors
   results[f'{width}x{height}']={'all_cues_fit':True,'card_fits_without_scroll':True,'ending_once':True,'cleanup':True};page.close()
  for width,height in [(1440,900),(1920,600),(900,800),(390,844),(320,568),(740,360)]:
   page=browser.new_page(viewport={'width':width,'height':height});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   def route(r):
    if '127.0.0.1' not in r.request.url:r.fulfill(content_type='application/json',body='{}')
    elif '/birthdayui.js' in r.request.url:r.fulfill(content_type='text/javascript',body=(ROOT/'src/frontend/js/birthdayui.js').read_text(encoding='utf8')+';window.__birthday={get scene(){return ctrl},get audio(){return music},get player(){return player}};')
    elif '/bdayscene-yuno.js' in r.request.url:
     s=(ROOT/'src/frontend/js/bdayscene-yuno.js').read_text(encoding='utf8').replace('return {whenReady,setBrightness','return {stopForTest(){cancelAnimationFrame(raf);raf=0},testPlan(){return skyPlan(TRK)},whenReady,setBrightness').replace('skySignDraw(c,f,age);c.restore();continue','window.__signMatrix=c.getTransform();skySignDraw(c,f,age);c.restore();continue').replace('if(depth>12){','window.__beam={sx,sy,bottom,depth,width,base};if(depth>12){')
     r.fulfill(content_type='text/javascript',body=s)
    else:r.continue_()
   page.route('**/*',route);page.goto(BASE+'/src/frontend/?bday=yuno&ufo=sign');page.wait_for_function('window.__birthday?.player')
   page.evaluate('()=>{__birthday.audio.pause();__birthday.scene.stopForTest();__birthday.scene.setIntro(()=>false)}');page.add_style_tag(content='#bday-bg,#bday-bg canvas{filter:brightness(1)!important}')
   data=page.evaluate('''()=>{
    const plan=__birthday.scene.testPlan(),f=plan.ufos[0];__birthday.scene.renderAt(f.birth+f.reveal+1);
    const m=window.__signMatrix,cv=document.querySelector('#bday-bg canvas'),rx=innerWidth/cv.width,ry=innerHeight/cv.height;
    const bounds={left:m.e*rx,right:(m.e+m.a*580)*rx,top:(m.f-m.d*30)*ry,bottom:(m.f+m.d*430)*ry};
    const scan=plan.ufos[1];__birthday.scene.renderAt(scan.birth+scan.arrive+scan.scan/2);
    return {bounds,beam:window.__beam,signTime:f.birth+f.reveal+1};
   }''')
   bounds=data['bounds'];assert bounds['left']>=0 and bounds['right']<=width and bounds['top']>=0 and bounds['bottom']<=height,(width,height,data)
   beam=data['beam'];assert beam['depth']>12 and beam['sy']<beam['bottom'] and beam['bottom']+beam['width']*.07<395,data
   page.screenshot(path=str(OUT/f'{width}x{height}-scan.png'));page.evaluate('t=>__birthday.scene.renderAt(t)',data['signTime']);page.screenshot(path=str(OUT/f'{width}x{height}-sign.png'))
   assert 'BGM' not in page.locator('.bday-track').inner_text()
   assert not errors,errors
   results[f'{width}x{height}'].update({'sign_fits':True,'beam_attached':True,'title_without_bgm':True});page.close()
  browser.close()
finally:server.shutdown()
(OUT/'results.json').write_text(json.dumps(results,sort_keys=True,indent=2)+'\n',encoding='utf8');print(json.dumps(results))

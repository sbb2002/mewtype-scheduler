"""인사말·플레이바 호버·왼쪽 손잡이 이동·일반 화면 조작 제거를 실제 브라우저로 검사."""
from pathlib import Path
import functools,http.server,threading,json,os,tempfile
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('BIRTHDAY_VERIFY_OUT',str(Path(tempfile.gettempdir())/'birthday-player-ui')))
OUT.mkdir(parents=True,exist_ok=True)
class Handler(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
 def copyfile(self,source,outputfile):
  try:super().copyfile(source,outputfile)
  except (ConnectionResetError,BrokenPipeError):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',8131),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
results={}
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,args=['--autoplay-policy=no-user-gesture-required'])
  for width,height,mobile in [(1440,900,False),(390,844,True),(360,800,True),(320,740,True)]:
   key=f'{width}x{height}';context=browser.new_context(viewport={'width':width,'height':height},is_mobile=mobile,has_touch=mobile,device_scale_factor=1)
   page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   def route(r):
    if '127.0.0.1' not in r.request.url:r.fulfill(content_type='application/json',body='{}')
    elif '/birthdayui.js' in r.request.url:
     r.fulfill(content_type='text/javascript',body=(ROOT/'src/frontend/js/birthdayui.js').read_text(encoding='utf8')+';window.__birthday={get scene(){return ctrl},get audio(){return music},get player(){return player},teardown};')
    else:r.continue_()
   page.route('**/*',route);page.goto('http://127.0.0.1:8131/src/frontend/?bday=yuno')
   page.wait_for_function('window.__birthday?.player && __birthday.audio');page.wait_for_timeout(350)
   page.evaluate('async()=>{__birthday.audio.pause();await __birthday.audio.seek(19.05)}')
   page.wait_for_function('document.documentElement.hasAttribute("data-bday-revealed")');page.wait_for_timeout(1450)
   bar=page.locator('.bday-music__bar');grip=page.locator('.bday-grip');cdp=context.new_cdp_session(page) if mobile else None
   def box():return bar.bounding_box()
   def background():return bar.evaluate('(e)=>({color:getComputedStyle(e).backgroundColor,opacity:+getComputedStyle(e).opacity})')
   greeting=page.evaluate('''()=>Object.fromEntries(['en','who'].map(key=>{const e=document.querySelector('.bday-greet__'+key),s=getComputedStyle(e),r=e.getBoundingClientRect();return [key,{weight:s.fontWeight,size:parseFloat(s.fontSize),left:r.left,right:r.right,top:r.top,bottom:r.bottom,opacity:s.opacity}]}))''')
   assert greeting['en']['weight']=='800' and greeting['who']['weight']=='700',greeting
   assert greeting['en']['size']>=30 and greeting['who']['size']>=19,greeting
   assert all(v['left']>=10 and v['right']<=width-10 for v in greeting.values()),greeting
   assert greeting['who']['top']>=greeting['en']['bottom'],greeting
   assert grip.bounding_box()['x']<page.locator('.bday-ib.prev').bounding_box()['x']
   assert page.locator('.bday-mini').count()==0
   page.screenshot(path=str(OUT/f'{key}-greeting.png'))
   # 배치 검사는 곡을 멈추고 장면 RAF를 쉬게 해 UI 동작을 분리해서 관찰한다.
   page.evaluate('()=>__birthday.scene.setStill(true)')
   if not mobile:
    page.mouse.move(2,2);page.wait_for_timeout(250);assert background()['color']=='rgba(18, 12, 28, 0.55)',background()
    page.locator('.bday-ib.pp').hover();page.wait_for_timeout(250);assert background()=={'color':'rgb(18, 12, 28)','opacity':1},background()
    page.wait_for_timeout(5200);assert background()['opacity']==1,background()
    page.screenshot(path=str(OUT/f'{key}-hover.png'))
    page.mouse.move(2,2);page.wait_for_timeout(300);assert background()['color']=='rgba(18, 12, 28, 0.55)',background()
   else:assert background()['color']=='rgba(18, 12, 28, 0.55)',background()
   def drag_to(dx=None,dy=None,end=None,release=True):
    before=box();g=grip.bounding_box();start=(g['x']+g['width']/2,g['y']+g['height']/2)
    target=end or (start[0]+dx,start[1]+dy)
    if mobile:
     cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':start[0],'y':start[1],'id':1}]})
     for n in range(1,9):cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':start[0]+(target[0]-start[0])*n/8,'y':start[1]+(target[1]-start[1])*n/8,'id':1}]})
    else:page.mouse.move(*start);page.mouse.down();page.mouse.move(*target,steps=8)
    page.wait_for_function('document.querySelector(".bday-music__bar").classList.contains("is-dragging")');page.wait_for_timeout(80)
    if release:
     if mobile:cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
     else:page.mouse.up()
     page.wait_for_function('!document.querySelector(".bday-music__bar").classList.contains("is-dragging")')
    assert page.evaluate('()=>document.documentElement.hasAttribute("data-bday-full")')
    return before,box()
   dx,dy=(-40,-150) if mobile else (-100,-180)
   before,after=drag_to(dx,dy);assert abs(after['x']-before['x']-dx)<2 and abs(after['y']-before['y']-dy)<2,(before,after)
   drag_to(end=(1,1));r=box();assert r['x']>=11.9 and r['y']>=11.9,r
   drag_to(end=(width-1,height-1));r=box();disc=page.locator('.bday-music__disc').bounding_box()
   assert r['x']+r['width']<=width-11.9 and r['y']+r['height']<=disc['y']-11.9,(r,disc)
   if mobile:
    t=page.locator('.bday-music__title').bounding_box();assert abs(t['x']+t['width']-(width-14))<2 and r['y']+r['height']<=t['y']-11.9 and t['y']+t['height']<=disc['y']-10,(t,r,disc)
    assert background()['color']=='rgba(18, 12, 28, 0.55)',background()
   page.screenshot(path=str(OUT/f'{key}-moved.png'))
   # 재생·볼륨 조작은 위치를 바꾸지 않는다.
   before=box();page.locator('.bday-ib.pp').click();page.wait_for_function('!__birthday.audio.paused')
   page.locator('.bday-ib.pp').click();page.wait_for_function('__birthday.audio.paused');assert box()==before
   if not mobile:
    r=page.locator('.bday-volume input').bounding_box();page.mouse.move(r['x']+r['width']*.2,r['y']+r['height']/2);page.mouse.down();page.mouse.move(r['x']+r['width']*.8,r['y']+r['height']/2,steps=5);page.mouse.up()
    assert page.evaluate('()=>__birthday.audio.volume')>.65 and box()==before
   grip.focus();before=box();page.keyboard.press('ArrowLeft');assert abs(box()['x']-before['x']+8)<1
   page.keyboard.press('Home');assert not bar.evaluate('(e)=>e.classList.contains("is-positioned")')
   drag_to(-25,-80);stored=box()
   page.evaluate('()=>__birthday.audio.play()');page.wait_for_timeout(150)
   page.locator('#bday-ui .bday-btn').click();page.wait_for_function('!document.documentElement.hasAttribute("data-bday-full")')
   assert not bar.is_visible() and page.locator('#bday-ui button').count()==1 and page.locator('.bday-mini').count()==0
   page.evaluate('()=>document.activeElement.blur()');state=page.evaluate('()=>({paused:__birthday.audio.paused,volume:__birthday.audio.volume,index:__birthday.audio.index,time:__birthday.audio.audio.currentTime})')
   page.keyboard.press('Space');page.keyboard.press('ArrowUp');page.keyboard.press('ArrowLeft');page.wait_for_timeout(180)
   current=page.evaluate('()=>({paused:__birthday.audio.paused,volume:__birthday.audio.volume,index:__birthday.audio.index,time:__birthday.audio.audio.currentTime})')
   assert not current['paused'] and current['volume']==state['volume'] and current['index']==state['index'] and current['time']>state['time'],(state,current)
   page.locator('#bday-ui .bday-btn').click();page.wait_for_function('document.documentElement.hasAttribute("data-bday-full")');page.wait_for_timeout(150)
   assert abs(box()['x']-stored['x'])<1 and abs(box()['y']-stored['y'])<1
   page.set_viewport_size({'width':844 if mobile else 390,'height':390 if mobile else 844});page.wait_for_timeout(200)
   r=box();vw=page.viewport_size['width'];vh=page.viewport_size['height'];assert r['x']>=11.9 and r['x']+r['width']<=vw-11.9 and r['y']+r['height']<=vh-11.9,r
   if mobile:
    drag_to(20,-40,release=False);cdp.send('Input.dispatchTouchEvent',{'type':'touchCancel','touchPoints':[]});page.wait_for_function('!document.querySelector(".bday-music__bar").classList.contains("is-dragging")')
   page.evaluate('()=>__birthday.teardown()');page.set_viewport_size({'width':width,'height':height});assert page.locator('#bday-music').count()==0
   assert not errors,errors
   results[key]={'greeting':greeting,'left_grip':True,'drag':True,'clamped':True,'controls_preserved':True,'keyboard':True,'no_mini':True,'normal_shortcuts_disabled':True,'resize':True,'cleanup':True,'errors':errors}
   context.close()
  browser.close()
finally:server.shutdown()
(OUT/'results.json').write_text(json.dumps(results,sort_keys=True,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(results,ensure_ascii=False,indent=2))

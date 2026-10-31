"""추가 연출의 실제 Chromium 캡처·휘도·CPU 측정."""
exec(open('scripts/verify_birthday_music.py',encoding='utf8').read().split('results={}')[0])
import numpy as np
from PIL import Image
import io
results={}
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--autoplay-policy=no-user-gesture-required'])
 page=b.new_page()
 errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 def route(r):
  if '127.0.0.1' not in r.request.url:r.fulfill(content_type='application/json',body='{}')
  elif '/birthdayui.js' in r.request.url:r.fulfill(content_type='text/javascript',body=(ROOT/'src/frontend/js/birthdayui.js').read_text(encoding='utf8')+';window.__birthday={get scene(){return ctrl},get audio(){return music},setFull};')
  else:r.continue_()
 page.route('**/*',route)
 page.goto(URL+'?bday=yuno');page.wait_for_function('window.__birthday?.scene && window.__birthday?.audio')
 page.wait_for_timeout(1500)
 page.evaluate('()=>__birthday.audio.pause()')
 times=[0,5,6.3,7,7.5,10,12,14,16,16.9,17,17.14,17.3,17.6,18,19]
 for w,h in [(1440,900),(390,844)]:
  page.set_viewport_size({'width':w,'height':h});page.wait_for_timeout(100)
  rows=[]
  for t in times:
   page.evaluate('async t=>{await __birthday.audio.seek(t);__birthday.scene.renderAt(t)}',t);page.wait_for_timeout(50)
   page.evaluate('async t=>{const m=await import("./js/bdaylogic.js");__birthday.scene.setIntro(()=>true);__birthday.scene.setBrightness(t>=17.14&&t<17.64?.3:m.introBrightness(t));__birthday.scene.renderAt(t)}',t)
   path=OUT/f'addendum-{w}-{t}.png';page.screenshot(path=str(path))
   rows.append(dict(t=t,**page.evaluate('()=>__birthday.scene.diagnostics().effect')))
  results[str(w)]=rows
  if w==1440:
   # 실제 최종 픽셀의 유노 조명이 부모 brightness에 다시 잘려 회색이 되지 않아야 한다.
   rgb=Image.open(OUT/'addendum-1440-7.5.png').convert('RGB').getpixel((720,400))
   results['spotlight_color']=rgb
   assert rgb[0]>150 and max(rgb)-min(rgb)>40,rgb
 # 실제 화면 평균 휘도를 30fps 곡 시각 간격으로 측정한다.
 for start,end in [(6.1,7.6),(17.1,18.7)]:
  values=[]
  for t in np.arange(start,end,1/30):
   page.evaluate('async t=>{await __birthday.audio.seek(t)}',float(t));page.wait_for_timeout(20);page.evaluate('async t=>{const m=await import("./js/bdaylogic.js");__birthday.scene.setIntro(()=>true);__birthday.scene.setBrightness(t>=17.14&&t<17.64?.3:m.introBrightness(t));__birthday.scene.renderAt(t)}',float(t))
   a=np.asarray(Image.open(io.BytesIO(page.screenshot())).convert('RGB'),dtype=float)
   values.append([float(t),float((a@np.array([.2126,.7152,.0722])).mean())])
  results[f'luminance-{start}']=values
 page.set_viewport_size({'width':1440,'height':900});page.wait_for_timeout(100)
 results['cpu']={}
 for t in [7.5,14,17.3]:
  costs=page.evaluate('t=>{for(let i=0;i<120;i++)__birthday.scene.renderAt(t+i/10000);return __birthday.scene.diagnostics().costs.slice(-120)}',t)
  results['cpu'][str(t)]={'mean':statistics.mean(costs),'p95':sorted(costs)[114],'max':max(costs)}
 page.emulate_media(reduced_motion='reduce');page.wait_for_timeout(100)
 results['reduced']=page.evaluate('()=>({raf:__birthday.scene.diagnostics().raf,effect:__birthday.scene.diagnostics().effect})')
 page.screenshot(path=str(OUT/'addendum-reduced.png'))
 results['errors']=errors
 b.close()
server.shutdown()
(OUT/'addendum.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'cpu':results['cpu'],'reduced':results['reduced'],'errors':errors},ensure_ascii=False))

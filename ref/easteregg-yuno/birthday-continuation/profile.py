from pathlib import Path
import functools,http.server,threading,json,statistics,sys
from playwright.sync_api import sync_playwright
ROOT=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
class Handler(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',8110),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
result={}
with sync_playwright() as p:
 browser=p.chromium.launch(headless='--headed' not in sys.argv,args=['--autoplay-policy=no-user-gesture-required'])
 page=browser.new_page(viewport={'width':1440,'height':900})
 def route(r):
  u=r.request.url
  if '127.0.0.1' not in u:r.fulfill(content_type='application/json',body='{}')
  elif '/birthdayui.js' in u:r.fulfill(content_type='text/javascript',body=(ROOT/'src/frontend/js/birthdayui.js').read_text(encoding='utf8')+';window.__birthday={get scene(){return ctrl},get audio(){return music}};')
  elif '/bdayscene-yuno.js' in u:
   s=(ROOT/'src/frontend/js/bdayscene-yuno.js').read_text(encoding='utf8')
   wrap='window.stageCosts={};\n'
   for name in ['bg','skyProps','floorWave','visual','skyUfos','front']:
    wrap+=f'const original_{name}={name};{name}=(...args)=>{{const start=performance.now();const result=original_{name}(...args);(window.stageCosts.{name}||=[]).push(performance.now()-start);return result}};\n'
   r.fulfill(content_type='text/javascript',body=s.replace(" const canvas=document.createElement('canvas');",wrap+" const canvas=document.createElement('canvas');"))
  else:r.continue_()
 page.route('**/*',route)
 page.goto('http://127.0.0.1:8110/src/frontend/?bday=yuno');page.wait_for_function('window.__birthday?.audio && window.__birthday?.scene');page.wait_for_timeout(1500)
 page.evaluate('()=>{__birthday.audio.pause();document.querySelector("#bday-bg").style.transform="translateX(300vw)"}')
 page.wait_for_timeout(200)
 result['renderer']=page.evaluate('()=>{const g=document.createElement("canvas").getContext("webgl");const e=g?.getExtension("WEBGL_debug_renderer_info");return e?g.getParameter(e.UNMASKED_RENDERER_WEBGL):null}')
 for t in [7.5,14,17.3,25,110]:
  result[str(t)]=page.evaluate('''async t=>{__birthday.scene.setIntro(()=>true);for(let i=0;i<5;i++){await new Promise(requestAnimationFrame);__birthday.scene.renderAt(t+i/10000)}window.stageCosts={};const a=[];for(let i=0;i<120;i++){await new Promise(requestAnimationFrame);const s=performance.now();__birthday.scene.renderAt(t+i/10000);a.push(performance.now()-s)}return {mean:a.reduce((a,b)=>a+b)/a.length,p95:a.toSorted((a,b)=>a-b)[114],stages:Object.fromEntries(Object.entries(stageCosts).map(([k,v])=>[k,v.reduce((a,b)=>a+b)/v.length]))}}''',t)
 browser.close()
server.shutdown()
Path(__file__).with_name('profile-headed.json' if '--headed' in sys.argv else 'profile.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result,indent=2))
